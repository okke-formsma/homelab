#!/usr/bin/env python3
"""Push a Lovelace dashboard YAML config to Home Assistant via WebSocket API.

Usage:
    source ../.env
    python3 push_dashboard.py garage/dashboard.yaml

The YAML file must have top-level keys:
    url_path, title, icon, show_in_sidebar, views
"""

import asyncio
import json
import os
import sys

import websockets
import yaml


def load_env():
    server = os.environ.get("HASS_SERVER")
    token = os.environ.get("HASS_TOKEN")
    if not server or not token:
        print("Error: HASS_SERVER and HASS_TOKEN must be set (source ../.env)")
        sys.exit(1)
    return server, token


async def push(config_path: str):
    server, token = load_env()
    ws_url = server.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    url_path = cfg.pop("url_path")
    title = cfg.pop("title")
    icon = cfg.pop("icon", "mdi:view-dashboard")
    show_in_sidebar = cfg.pop("show_in_sidebar", True)
    # remaining keys (views, etc.) become the lovelace config
    dashboard_config = cfg

    print(f"Pushing '{title}' (/{url_path}) to {server}")

    async with websockets.connect(ws_url) as ws:
        msg = json.loads(await ws.recv())
        assert msg["type"] == "auth_required"
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        msg = json.loads(await ws.recv())
        assert msg["type"] == "auth_ok", f"Auth failed: {msg}"

        # Create dashboard (ignore error if it already exists)
        await ws.send(json.dumps({
            "id": 1, "type": "lovelace/dashboards/create",
            "url_path": url_path, "title": title, "icon": icon,
            "show_in_sidebar": show_in_sidebar, "require_admin": False,
        }))
        r = json.loads(await ws.recv())
        if r.get("success"):
            print(f"  Created dashboard /{url_path}")
        else:
            print(f"  Dashboard already exists (or error: {r.get('error',{}).get('message','')}), updating config...")

        # Save config
        await ws.send(json.dumps({
            "id": 2, "type": "lovelace/config/save",
            "url_path": url_path,
            "config": dashboard_config,
        }))
        r = json.loads(await ws.recv())
        if r.get("success"):
            print(f"  Config saved OK")
        else:
            print(f"  Failed to save config: {r.get('error')}")
            sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <dashboard.yaml>")
        sys.exit(1)
    asyncio.run(push(sys.argv[1]))
