#!/usr/bin/env python3
"""Generate a Lovelace dashboard YAML from a compact config.

Usage:
    uv run python3 generate_dashboard.py garage/dashboard_config.yaml

Writes the output to dashboard.yaml in the same directory as the config.
"""

import sys
from pathlib import Path

import yaml


# ── Custom EVAL tooltip used by some charts ──────────────────────────────────

CUSTOM_TOOLTIP = (
    "EVAL:function({seriesIndex, dataPointIndex, w}) {"
    " var x = w.globals.seriesX[seriesIndex][dataPointIndex];"
    " var h = '<div style=\"padding:6px 10px;font-size:12px\">';"
    " for (var i = 0; i < w.globals.seriesNames.length; i++) {"
    " var xs = w.globals.seriesX[i]; var n = 0, m = 1/0;"
    " for (var j = 0; j < xs.length; j++) { var d = Math.abs(xs[j] - x); if (d < m) { m = d; n = j; } }"
    " if (m > 600000) continue;"
    " var v = w.globals.series[i][n]; if (v == null) continue;"
    " var c = w.globals.colors[i];"
    " h += '<div style=\"display:flex;align-items:center;gap:6px;padding:3px 0\">"
    "<span style=\"background:' + c + ';width:12px;height:12px;border-radius:50%;"
    "display:inline-block\"></span> ' + w.globals.seriesNames[i] + ': <b>' + "
    "(Math.round(v * 10) / 10) + '</b></div>'; }"
    " return h + '</div>'; }"
)


# ── Color thresholds (Jinja templates) ───────────────────────────────────────

COLOR_TEMPLATES = {
    "co2": (
        "{{% set v = states('{entity}')|float(0) %}}"
        " {{% if v <= 800 %}}green{{% elif v <= 1200 %}}orange{{% else %}}red{{% endif %}}"
    ),
    "humidity": (
        "{{% set v = states('{entity}')|float(0) %}}"
        " {{% if 40 <= v <= 60 %}}green{{% else %}}red{{% endif %}}"
    ),
    "temperature": (
        "{{% set v = states('{entity}')|float(0) %}}"
        " {{% if v < 15 %}}blue{{% elif v < 18 %}}amber{{% elif v <= 24 %}}green"
        "{{% elif v <= 30 %}}orange{{% else %}}red{{% endif %}}"
    ),
    "valve_position": (
        "{{% set v = states('{entity}')|float(0) %}}"
        " {{% if v == 0 %}}red{{% else %}}grey{{% endif %}}"
    ),
}

SENSOR_DISPLAY = {
    "co2":            {"icon": "mdi:molecule-co2",  "suffix": "",  "round": 0},
    "humidity":       {"icon": "mdi:water-percent", "suffix": "%", "round": 0},
    "temperature":    {"icon": "mdi:thermometer",   "suffix": "°", "round": 1},
    "valve_position": {"icon": "mdi:valve",         "suffix": "%", "round": 0},
}


# ── Builders ─────────────────────────────────────────────────────────────────

def build_fan_top_cards(fan_cfg):
    """The two fan status cards at the top (fan control + RPM)."""
    bg_style = "ha-card { background: none !important; box-shadow: none !important; border: none !important; "

    def overlay_card(graph_entity, overlay):
        return {
            "type": "custom:stack-in-card",
            "card_mod": {"style": "ha-card { overflow: hidden; height: 70px; }"},
            "cards": [
                {
                    "type": "custom:mini-graph-card",
                    "entities": [{"entity": graph_entity, "color": "rgba(var(--rgb-primary-color), 0.15)"}],
                    "hours_to_show": 24, "line_width": 2, "height": 55,
                    "show": {"name": False, "icon": False, "state": False, "labels": False, "points": False, "fill": "fade"},
                    "card_mod": {"style": bg_style + "margin-top: -8px; }"},
                },
                {**overlay, "card_mod": {"style": bg_style + "margin-top: -72px; position: relative; z-index: 1; }"}},
            ],
        }

    return {
        "type": "grid", "columns": 2, "square": False,
        "cards": [
            overlay_card(fan_cfg["speed_entity"], {
                "type": "custom:mushroom-fan-card",
                "entity": fan_cfg["entity"],
                "name": "Fan",
                "icon_animation": True,
            }),
            overlay_card(fan_cfg["rpm_entity"], {
                "type": "custom:mushroom-entity-card",
                "entity": fan_cfg["rpm_entity"],
                "name": "RPM",
                "icon": "mdi:rotate-right",
            }),
        ],
    }


def build_room_card(room):
    """A single room status card (header + 2x2 sensor grid)."""
    prefix = room["entity_prefix"]
    sensors = []
    for key, display in SENSOR_DISPLAY.items():
        entity = f"sensor.{prefix}_{key}"
        r = display["round"]
        primary = "{{ " + f"states('{entity}')|round({r})" + " }}" + display["suffix"]
        card = {
            "type": "custom:mushroom-template-card",
            "primary": primary,
            "icon": display["icon"],
            "icon_color": COLOR_TEMPLATES[key].format(entity=entity),
            "layout": "vertical",
            "tap_action": {"action": "none"},
        }
        sensors.append(card)

    return {
        "type": "custom:stack-in-card",
        "cards": [
            {
                "type": "custom:mushroom-template-card",
                "primary": room["name"],
                "icon": room["icon"],
                "icon_color": room["color"],
                "layout": "vertical",
                "tap_action": {
                    "action": "navigate",
                    "navigation_path": f"/config/devices/device/{room['device_id']}",
                },
            },
            {
                "type": "grid", "columns": 2, "square": False,
                "cards": sensors,
            },
        ],
    }


def build_room_status_grid(rooms):
    """The 5-column room status grid."""
    return {
        "type": "grid", "columns": 5, "square": False,
        "cards": [build_room_card(r) for r in rooms],
    }


def build_series(rooms, sensor):
    """Build the per-room series list for an apexcharts-card."""
    return [
        {
            "entity": f"sensor.{r['entity_prefix']}_{sensor}",
            "name": r["name"],
            "color": r["hex"],
            "stroke_width": 2,
            "extend_to": "now",
            "fill_raw": "last",
            "group_by": {"func": "last", "duration": "5min", "fill": "last"},
        }
        for r in rooms
    ]


def build_tooltip_shared():
    return {
        "enabled": True, "shared": True, "intersect": False,
        "followCursor": True,
        "fixed": {"enabled": True, "position": "topLeft"},
        "x": {"show": False},
    }


def build_tooltip_custom():
    return {
        "followCursor": True,
        "fixed": {"enabled": True, "position": "topLeft"},
        "custom": CUSTOM_TOOLTIP,
    }


def build_apex_chart(graph_cfg, all_rooms):
    """Build a single apexcharts-card from graph config."""
    yaxis_cfg = graph_cfg.get("yaxis", {})
    yaxis = [{}]
    for k in ("min", "max"):
        if k in yaxis_cfg:
            yaxis[0][k] = yaxis_cfg[k]
    apex_sub = {}
    if "tickAmount" in yaxis_cfg:
        apex_sub["tickAmount"] = yaxis_cfg["tickAmount"]
    apex_sub["forceNiceScale"] = True
    yaxis[0]["apex_config"] = apex_sub

    tooltip = (build_tooltip_custom() if graph_cfg.get("tooltip") == "custom"
               else build_tooltip_shared())

    # Filter rooms if specified
    room_names = graph_cfg.get("rooms")
    if room_names:
        rooms = [r for r in all_rooms if r["name"] in room_names]
    else:
        rooms = all_rooms

    return {
        "type": "custom:apexcharts-card",
        "header": {"show": False},
        "graph_span": "24h",
        "yaxis": yaxis,
        "apex_config": {
            "title": {
                "text": graph_cfg["title"],
                "floating": True, "offsetY": 6, "align": "center",
                "style": {"fontSize": "14px", "fontWeight": "600"},
            },
            "chart": {"height": 180},
            "stroke": {"width": 2},
            "legend": {"show": False},
            "tooltip": tooltip,
        },
        "series": build_series(rooms, graph_cfg["sensor"]),
    }


def build_fan_chart(fan_cfg):
    """The special dual-axis fan chart."""
    tooltip = build_tooltip_custom()
    return {
        "type": "custom:apexcharts-card",
        "header": {"show": False},
        "graph_span": "24h",
        "yaxis": [
            {"id": "speed", "min": 0, "max": 100},
            {"id": "rpm", "opposite": True, "min": 0},
        ],
        "apex_config": {
            "title": {
                "text": "Fan",
                "floating": True, "offsetY": 6, "align": "center",
                "style": {"fontSize": "14px", "fontWeight": "600"},
            },
            "chart": {"height": 180},
            "stroke": {"width": 2},
            "legend": {"show": False},
            "tooltip": tooltip,
        },
        "series": [
            {
                "entity": fan_cfg["speed_entity"], "name": "Speed %",
                "stroke_width": 2, "yaxis_id": "speed",
                "extend_to": "now", "fill_raw": "last",
                "group_by": {"func": "last", "duration": "5min", "fill": "last"},
            },
            {
                "entity": fan_cfg["rpm_entity"], "name": "RPM",
                "stroke_width": 2, "yaxis_id": "rpm",
                "extend_to": "now", "fill_raw": "last",
                "group_by": {"func": "last", "duration": "5min", "fill": "last"},
            },
        ],
    }


def build_graph_grids(graph_pairs, all_rooms, fan_cfg):
    """Build the graph section: pairs of charts in 2-column grids."""
    grids = []
    for pair in graph_pairs:
        cards = []
        for g in pair:
            if g.get("special") == "fan":
                cards.append(build_fan_chart(fan_cfg))
            elif "sensor" in g:
                cards.append(build_apex_chart(g, all_rooms))
        grids.append({
            "type": "grid", "columns": 2, "square": False,
            "cards": cards,
        })
    return grids


# ── Main ─────────────────────────────────────────────────────────────────────

def generate(config_path: str):
    config_path = Path(config_path)
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    rooms = cfg["rooms"]
    fan = cfg["fan"]
    view_cfg = cfg["view"]

    view_cards = [
        build_fan_top_cards(fan),
        build_room_status_grid(rooms),
        *build_graph_grids(cfg["graphs"], rooms, fan),
    ]

    dashboard = {
        "url_path": cfg["url_path"],
        "title": cfg["title"],
        "icon": cfg.get("icon", "mdi:view-dashboard"),
        "show_in_sidebar": cfg.get("show_in_sidebar", True),
        "views": [{
            "title": view_cfg["title"],
            "path": view_cfg["path"],
            "icon": view_cfg["icon"],
            "panel": True,
            "cards": [{
                "type": "vertical-stack",
                "cards": view_cards,
            }],
        }],
    }

    out_path = config_path.parent / "dashboard.yaml"
    with open(out_path, "w") as f:
        f.write("# AUTO-GENERATED — edit dashboard_config.yaml, then run generate_dashboard.py\n")
        yaml.dump(dashboard, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"Generated {out_path} ({sum(1 for _ in open(out_path))} lines)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <dashboard_config.yaml>")
        sys.exit(1)
    generate(sys.argv[1])
