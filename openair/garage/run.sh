#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

esphome run open-air-mini.yaml --no-logs --device 192.168.1.205
esphome run valve-1.yaml --no-logs --device 192.168.1.144
esphome run valve-2.yaml --no-logs --device 192.168.1.190
esphome run valve-3.yaml --no-logs --device 192.168.1.229
esphome run valve-4.yaml --no-logs --device 192.168.1.4
esphome run valve-5.yaml --no-logs --device 192.168.1.234
