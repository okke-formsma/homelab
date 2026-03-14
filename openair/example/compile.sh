#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

esphome compile \
  fan-controller.yaml \
  valve-1.yaml \
  valve-2.yaml
