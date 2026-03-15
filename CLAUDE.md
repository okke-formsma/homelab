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

## Flashing ESPHome devices

ESPHome is managed via a uv project in `openair/`. The venv must be active when running `run.sh`.

```bash
cd openair
uv sync          # first time only
source .venv/bin/activate
bash garage/run.sh
bash huis/run.sh
```
