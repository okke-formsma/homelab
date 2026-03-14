#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

esphome run fan-controller.yaml --no-logs
esphome run valve-1.yaml --no-logs
esphome run valve-2.yaml --no-logs
