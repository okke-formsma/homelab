# Homelab

## Flashing ESPHome devices

ESPHome is managed via a uv project in `openair/`. The venv must be active when running `run.sh`.

```bash
cd openair
uv sync          # first time only
source .venv/bin/activate
bash garage/run.sh
bash huis/run.sh
```
