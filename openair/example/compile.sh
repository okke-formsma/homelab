#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

esphome compile \
  fan-controller.yaml \
  valve.yaml
