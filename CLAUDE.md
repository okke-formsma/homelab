# Homelab

## Home Assistant API

Use the HA REST API directly. Connection config is in `.env` (gitignored):

```bash
source .env
# List all states
curl -s -H "Authorization: Bearer $HASS_TOKEN" "$HASS_SERVER/api/states" | python3 -m json.tool

# Get a single entity
curl -s -H "Authorization: Bearer $HASS_TOKEN" "$HASS_SERVER/api/states/sensor.some_entity"

# Call a service
curl -s -X POST -H "Authorization: Bearer $HASS_TOKEN" -H "Content-Type: application/json" \
  "$HASS_SERVER/api/services/domain/service" -d '{"entity_id": "..."}'
```

The `.env` and `.claude/settings.local.json` are gitignored — never commit them.

For Python scripts that interact with HA (e.g. websocket API), use the `uv` environment in `openair/`:

```bash
cd openair
uv add websockets   # install extra deps as needed
uv run python3 my_script.py
```

## Dashboard

The Open AIR dashboard is generated from a compact config:

```bash
cd openair
uv run python3 generate_dashboard.py garage/dashboard_config.yaml
source ../.env && uv run python3 push_dashboard.py garage/dashboard.yaml
```

**Theme dependency:** The dashboard uses an `openair` theme to remove card borders.
This file lives on the HA instance (not in this repo) and must exist for borderless cards:

```
# /config/themes/openair.yaml on the HA instance
openair:
  ha-card-border-width: 0px
```

To create/recreate it: `ssh root@homeassistant.griffin-court.ts.net`, then:

```bash
mkdir -p /config/themes
cat > /config/themes/openair.yaml << 'EOF'
openair:
  ha-card-border-width: 0px
EOF
```

Then reload themes via HA: Developer Tools → Services → `frontend.reload_themes`.

Why a theme? `card_mod` per-card CSS doesn't survive SPA back-navigation because
HA's shadow DOM prevents CSS variable inheritance. Only a real HA theme sets
`--ha-card-border-width` at the right scope.

## Flashing ESPHome devices

ESPHome is managed via a uv project in `openair/`. The venv must be active when running `run.sh`.

```bash
cd openair
uv sync          # first time only
source .venv/bin/activate
bash garage/run.sh
bash huis/run.sh
```
