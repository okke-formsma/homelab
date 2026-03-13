#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

esphome run fan-controller.yaml --no-logs
esphome run valve.yaml --no-logs
