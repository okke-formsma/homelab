# Homelab

## Home Assistant CLI

Use `hass-cli` for all HA interactions. Connection config is in `.env` (gitignored):

```bash
source .env
hass-cli state list
hass-cli entity list
```

The `.env` and `.claude/settings.local.json` are gitignored — never commit them.

## Flashing ESPHome devices

ESPHome is managed via a uv project in `openair/`. The venv must be active when running `run.sh`.

```bash
cd openair
uv sync          # first time only
source .venv/bin/activate
bash garage/run.sh
bash huis/run.sh
```
