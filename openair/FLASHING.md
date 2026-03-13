# Flashing

## Setup

```bash
# Install ESPHome (managed by uv)
uv sync

# First-time secrets (do this once per directory)
cp secrets.yaml.example secrets.yaml          # fill in WiFi + keys
cp valves/secrets.yaml.example valves/secrets.yaml
```

## Flash / update

```bash
# Fan controllers (from openair/)
esphome run open-air-mini-garage.yaml
esphome run open-air-mini-huis.yaml

# Valves (from openair/)
cd valves && esphome run valve1.yaml     # garage valves
cd valves && esphome run huis-valve-1.yaml  # huis valves
```

Pass `--device <IP>` if mDNS resolution is slow or fails on first flash:

```bash
esphome run open-air-mini-garage.yaml --device 192.168.1.x
```

## Logs

```bash
esphome logs open-air-mini-garage.yaml
cd valves && esphome logs valve1.yaml
```
