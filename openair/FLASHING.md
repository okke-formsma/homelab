## How to flash

The ip's can be ignored after the first time.

  workon esphome
  pip install --update esphome
  esphome run open-air-mini-huis.yaml --device 192.168.1.244
  esphome logs open-air-mini-huis.yaml --device 192.168.1.244
  esphome run open-air-mini-garage.yaml --device 192.168.1.205
  cd valves && esphome run valve1.yaml
