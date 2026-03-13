# Local Mode — How it works today

**[▶ Open simulator](https://formsma.nl/homelab/openair/simulator.html)** — interactive tool to explore how the fan and valves respond to sensor readings.

> Flashing instructions: see [FLASHING.md](FLASHING.md)

## Overview

Local Mode is a fallback/standalone control system for the ventilation setup. It allows the fan and valves to operate **without Home Assistant**. It activates when:
- The HA API connection is lost, **or**
- The "Local Mode" toggle switch is turned on manually

## Architecture

Each fan controller manages its own set of valves independently. Multiple installations run in parallel without interaction.

```
┌──────────────────────────────────────────────┐   ┌──────────────────────────────────────────┐
│  open-air-mini-garage (5 valves)              │   │  open-air-mini-huis (4 valves)            │
│  ESP32 + fan (PWM on GPIO15)                 │   │  ESP32 + fan (PWM on GPIO15)             │
│  Polls valves via HTTP every 60s             │   │  Polls valves via HTTP every 60s         │
│  Exposes fan speed for valves to read        │   │  Exposes fan speed for valves to read    │
└────────────┬─────────────────────────────────┘   └────────────┬─────────────────────────────┘
             │ HTTP GET /sensor/{CO2,Humidity}                   │ HTTP GET /sensor/{CO2,Humidity}
             ▼                                                   ▼
     valve-1 .. valve-5                                valve-huis-1 .. valve-huis-4
       (each polls fan speed back via HTTP)              (each polls fan speed back via HTTP)
```

The system supports 2–7 valves per controller. Unused slots are set to `"0.0.0.0"` in the controller yaml — they fail silently (NAN) and are excluded from demand calculation.

## Setting up a new installation

> For flashing instructions see [FLASHING.md](FLASHING.md)

Each installation is a fan controller + N valves (2–7). The only files you need to create or edit per installation are:

**Fan controller** (e.g. `open-air-mini-garage.yaml`):

```yaml
packages:
  local_mode: !include local_mode_fan.yaml

substitutions:
  valve_1_host: "open-air-valve-1.local"   # set one line per active valve
  valve_2_host: "open-air-valve-2.local"   # unused slots default to "0.0.0.0"
  # ...

esphome:
  name: open-air-mini-<yourname>
# ... hardware config (GPIO, fan, sensors) ...
```

**Valve** (e.g. `valves/valve1.yaml`):

```yaml
substitutions:
  devicename: open-air-valve-1
  upper_devicename: Open AIR Valve 1
  fan_host: "open-air-mini-<yourname>.local"  # only needed if != garage default

<<: !include Open_AIR_Valve_DIS_SCD40_SGP41.yaml
```

**Secrets** (copy once per directory, never commit):

```bash
cp secrets.yaml.example secrets.yaml
cp valves/secrets.yaml.example valves/secrets.yaml
```

Unused valve slots in `local_mode_fan.yaml` default to `"0.0.0.0"` — HTTP requests to that address fail immediately and return NAN, which is excluded from demand calculation. No special handling needed.

## Shared settings (`local_mode_settings.yaml`)

All tuning parameters live in one file, included by both the fan controller and every valve:

| Parameter | Value | Purpose |
|---|---|---|
| `co2_target` | 600 ppm | Below this = no demand |
| `co2_max` | 1500 ppm | Full demand |
| `humidity_target` | 60% | Below this = no demand |
| `humidity_max` | 75% | Full demand |
| `fan_speed_min` | 15% | Always-on minimum |
| `fan_speed_max` | 70% | Maximum speed |
| `valve_pos_min` | 0.05 | Keep slightly open for sensor freshness |
| `valve_pos_max` | 1.0 | Fully open |
| `dead_band` | 0.05 | Below this fan demand, all valves open fully |
| `smoothing_alpha` | 0.7 | EMA weight on new value (higher = less smoothing) |
| `poll_interval` | 60s | How often to poll and recompute |
| `fan_host` | open-air-mini-garage.local | Hostname valves use to poll fan speed — override per valve for other installations |

## Shared helpers (`local_mode_helpers.h`)

- `parse_sensor_value(body, status_code)` — extracts the `"value"` field from ESPHome web server JSON responses. Returns NAN on failure.
- `compute_demand(value, target, max_val)` — maps a sensor value to 0-1 demand using linear interpolation between target and max.
- `ema(old_value, new_value, alpha)` — exponential moving average for smoothing.

## Fan control (`local_mode_fan.yaml` — shared by all controllers)

Every poll cycle, the openair controller:

1. **Polls CO2 + humidity** from all configured valves via HTTP (2 requests per slot, up to 14 total)
2. **Computes per-valve demand** (0-1) using `compute_demand()` — linear interpolation between target and max, taking the higher of CO2 and humidity demand
3. **Fan demand = max demand** across all reachable valves (the neediest room drives the fan)
4. **Applies EMA smoothing** to prevent jitter
5. **Maps to fan speed**: `fan_speed_min + smoothed_demand * (fan_speed_max - fan_speed_min)`

Valves that return NAN (unreachable or sensor error) are excluded from the calculation — they simply don't contribute to demand. The system keeps running on whatever valves are reachable, worst case at minimum fan speed.

The fan speed is exposed via the ESPHome web server at `/fan/Open AIR Mini`, which valves poll to coordinate.

## Valve control (each valve — `local_mode_valve.yaml`)

Each valve runs independently every poll cycle:

1. **Reads own CO2 + humidity** from local I2C sensors (no HTTP needed)
2. **Polls current fan speed** from the openair controller via HTTP GET
3. **Computes own demand** (0-1) using the same `compute_demand()` formula
4. **Applies EMA smoothing** to its demand signal
5. **Computes valve position** using the fan speed to coordinate with other rooms:

```
fan_demand = normalize fan speed to 0-1

if fan unreachable or fan_speed <= 0:
    position = fully open (safe default)
elif fan_demand < dead_band:
    position = fully open (no meaningful demand signal, prevent hunting)
else:
    ratio = smoothed_demand / fan_demand  (clamped 0-1)
    position = valve_pos_min + ratio * (valve_pos_max - valve_pos_min)
```

This naturally balances airflow: if this room is driving the fan (ratio ≈ 1), the valve stays wide open. If another room is driving the fan (ratio < 1), this valve closes down to redirect airflow where it's needed.

Valve positioning uses a 101-entry lookup table that maps 0-100% to stepper motor steps (0-525), accounting for the non-linear relationship between valve position and airflow.

Valve control is skipped during homing (`homing_in_progress` flag).

## Assumptions and approximations

### Fan speed is driven by the single worst room
Fan demand equals the maximum demand across all valves. The fan runs at the same speed whether 1 room or 5 rooms need air at the same demand level. With more valves open, total system resistance drops and the fan delivers more total flow at the same speed — so the physics partially self-correct. But with 5 rooms all demanding, each gets roughly 1/5th the airflow compared to a single room, so CO2 clears slower. Given the Ducobox Silent's 400 m³/h capacity, even split across 5 rooms this is 80 m³/h per room at full speed, which is typically sufficient.

### Linearity assumption in valve coordination
The valve position formula (`ratio = demand / fan_demand`) assumes airflow through a valve scales linearly with its opening. The lookup table compensates for the non-linear valve mechanics (position → stepper steps), but the distribution of airflow across parallel ducts also depends on duct lengths, diameters, and bends. Without per-duct flow measurement, this is the best practical approximation.

### No flow rate awareness
The system controls PWM percentage, not actual airflow (m³/h). The fan curve (RPM → m³/h at different backpressures) is unknown and would require expensive measurement equipment to characterize.
