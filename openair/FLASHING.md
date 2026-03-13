# Flashing

## Setup (first time)

```bash
# Install ESPHome
uv sync

# Create secrets file (covers all installations — ESPHome searches up from config dir)
cp secrets.yaml.example secrets.yaml   # fill in WiFi credentials + keys
```

## Flash / update

Run from the `openair/` directory:

```bash
# Fan controllers
esphome run garage/open-air-mini.yaml
esphome run huis/open-air-mini.yaml

# Valves
esphome run garage/valve-1.yaml
esphome run huis/valve-1.yaml
```

Pass `--device <IP>` on first flash (before mDNS is set up):

```bash
esphome run garage/open-air-mini.yaml --device 192.168.x.x
```

## Logs

```bash
esphome logs garage/open-air-mini.yaml
esphome logs garage/valve-1.yaml
```
