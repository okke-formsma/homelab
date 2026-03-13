#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

esphome run open-air-mini.yaml --no-logs --device open-air-mini-huis.local
esphome run valve-1.yaml --no-logs --device open-air-valve-huis-1.local
esphome run valve-2.yaml --no-logs --device open-air-valve-huis-2.local
esphome run valve-3.yaml --no-logs --device open-air-valve-huis-3.local
esphome run valve-4.yaml --no-logs --device open-air-valve-huis-4.local
