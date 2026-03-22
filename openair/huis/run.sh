#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Valve 1 (Bathroom) - RH & temp only - currently misnamed as open-air-valve-3-20950c
esphome run valve-1.yaml --no-logs --device 192.168.1.62
# Valve 2 (Master Bedroom) - CO2, RH, temp
esphome run valve-2.yaml --no-logs --device 192.168.1.245
# Valve 3 (Toilet) - CO2, RH, temp, NOx, VOC
esphome run valve-3.yaml --no-logs --device 192.168.1.56

# Valve 4 (Living Room) - full sensor set - not powered up yet
# esphome run valve-4.yaml --no-logs --device open-air-valve-huis-4.local

# Mini fan controller
esphome run open-air-mini.yaml --no-logs --device 192.168.1.244
