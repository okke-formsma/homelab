# OpenAIR Local Mode

**[▶ Open simulator](https://formsma.nl/homelab/openair/simulator.html)** — interactive tool to explore how the fan and valves respond to sensor readings.

Local Mode is a standalone control system that lets the fan and valves operate **without Home Assistant**. It activates when:
- The HA API connection is lost, **or**
- The "Local Mode" toggle switch is turned on manually

## Architecture

Each fan controller manages its own set of valves independently. Multiple installations run in parallel without interaction.

```
┌────────────────────────────────────┐   ┌────────────────────────────────────┐
│  open-air-mini-garage (5 valves)   │   │  open-air-mini-huis (4 valves)     │
│  Polls valves via HTTP every 60s   │   │  Polls valves via HTTP every 60s   │
│  Exposes fan speed via web server  │   │  Exposes fan speed via web server  │
└──────────────┬─────────────────────┘   └──────────────┬─────────────────────┘
               │ HTTP GET /sensor/{CO2,Humidity}         │ HTTP GET /sensor/{CO2,Humidity}
               ▼                                         ▼
       valve-1 .. valve-5                        valve-1 .. valve-4
         (each polls fan speed back)               (each polls fan speed back)
```

Unused valve slots in `local_mode_fan.yaml` default to `"0.0.0.0"`. Requests to that address fail immediately, return NAN, and are excluded from demand calculation — no special handling needed.

## Shared settings (`shared/local_mode_settings.yaml`)

All tuning parameters live in one file, included by both the fan controller and every valve:

| Parameter | Default | Purpose |
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

## Shared helpers (`shared/local_mode_helpers.h`)

- `parse_sensor_value(body, status_code)` — extracts the `"value"` field from ESPHome web server JSON responses. Returns NAN on failure.
- `compute_demand(value, target, max_val)` — maps a sensor value to 0-1 demand using linear interpolation between target and max.
- `ema(old_value, new_value, alpha)` — exponential moving average for smoothing.

## Fan control (`shared/local_mode_fan.yaml`)

Every poll cycle, the fan controller:

1. **Polls CO2 + humidity** from all configured valves via HTTP (2 requests per slot, up to 14 total)
2. **Computes per-valve demand** (0–1) — linear interpolation between target and max, taking the higher of CO2 and humidity demand
3. **Fan demand = max demand** across all reachable valves (the neediest room drives the fan)
4. **Applies EMA smoothing** to prevent jitter
5. **Sets fan speed**: `fan_speed_min + smoothed_demand × (fan_speed_max − fan_speed_min)`

Valves returning NAN (unreachable or sensor error) are excluded. The system keeps running on whatever valves are reachable — worst case at minimum fan speed.

The fan speed is exposed via the ESPHome web server at `/fan/Open AIR Mini`, which valves poll to coordinate.

## Valve control (`shared/local_mode_valve.yaml`)

Each valve runs independently every poll cycle:

1. **Reads own CO2 + humidity** from local I2C sensors
2. **Polls current fan speed** from the fan controller via HTTP GET
3. **Computes own demand** (0–1) using the same formula
4. **Applies EMA smoothing**
5. **Sets valve position** using the fan speed to coordinate with other rooms:

```
fan_demand = normalize fan speed to 0-1

if fan unreachable or fan_speed <= 0:
    position = fully open (safe default)
elif fan_demand < dead_band:
    position = fully open (no meaningful signal, prevent hunting)
else:
    ratio = smoothed_demand / fan_demand  (clamped 0-1)
    position = valve_pos_min + ratio × (valve_pos_max − valve_pos_min)
```

If this room is driving the fan (ratio ≈ 1), the valve stays wide open. If another room is driving the fan (ratio < 1), this valve closes down to redirect airflow where it's needed.

Valve positioning uses a 101-entry lookup table mapping 0–100% to stepper motor steps (0–525), accounting for the non-linear relationship between valve position and airflow.

Valve control is skipped during homing (`homing_in_progress` flag).

## Assumptions and approximations

### Fan speed is driven by the single worst room
Fan demand equals the maximum demand across all valves. The fan runs at the same speed whether 1 room or 5 rooms need air at the same demand level. With more valves open, total system resistance drops and the fan delivers more total flow at the same speed — so the physics partially self-correct. But with 5 rooms all demanding, each gets roughly 1/5th the airflow compared to a single room, so CO2 clears slower. Given the Ducobox Silent's 400 m³/h capacity, even split across 5 rooms this is 80 m³/h per room at full speed, which is typically sufficient.

### Linearity assumption in valve coordination
The valve position formula (`ratio = demand / fan_demand`) assumes airflow through a valve scales linearly with its opening. The lookup table compensates for the non-linear valve mechanics (position → stepper steps), but the distribution of airflow across parallel ducts also depends on duct lengths, diameters, and bends. Without per-duct flow measurement, this is the best practical approximation.

### No flow rate awareness
The system controls PWM percentage, not actual airflow (m³/h). The fan curve (RPM → m³/h at different backpressures) is unknown and would require expensive measurement equipment to characterize.

---

## Repository layout

```
openair/
  shared/          ← shared logic — never edit these
  garage/          ← garage installation (fan controller + 5 valves)
  huis/            ← huis installation (fan controller + 4 valves)
  example/         ← copy this to start a new installation
  secrets.yaml     ← gitignored, one file covers all installations
```

Each installation directory contains:

| File | Purpose |
|---|---|
| `config.yaml` | All user-configurable settings: `device_name`, `fan_host`, valve hostnames |
| `open-air-mini.yaml` | Fan controller: hardware config only (no user edits needed) |
| `valve-N.yaml` | One file per valve: device name + includes config + hardware template |

## Setting up a new installation

### 1. Create a directory

```bash
mkdir myhouse
```

### 2. Create `myhouse/config.yaml`

Copy from `example/config.yaml`. Fill in your device name and valve hostnames:

```yaml
substitutions:
  device_name: "open-air-mini-myhouse"
  fan_host: "${device_name}.local"

  valve_1_host: "open-air-valve-myhouse-1.local"
  valve_2_host: "open-air-valve-myhouse-2.local"
  valve_3_host: "open-air-valve-myhouse-3.local"
  # Unused slots default to "0.0.0.0" in local_mode_fan.yaml — no need to list them
```

`fan_host` is automatically derived from `device_name`, so you only need to set the name once.

### 3. Create `myhouse/open-air-mini.yaml`

Copy from `example/fan-controller.yaml` without modification. All installation-specific values come from `config.yaml`.

### 4. Create `myhouse/valve-N.yaml` for each valve

Copy from `example/valve.yaml`. Fill in `devicename` and `upper_devicename`.
`fan_host` comes automatically from `config.yaml`.

```yaml
substitutions:
  devicename: open-air-valve-myhouse-1
  upper_devicename: Open AIR Valve Myhouse 1

packages:
  config: !include config.yaml
  hardware: !include ../shared/Open_AIR_Valve_DIS_SCD40_SGP41.yaml

esphome:
  includes:
    - ../shared/local_mode_helpers.h
```

Repeat for each valve, incrementing the number.

### 5. Secrets

Create `secrets.yaml` at the `openair/` root if it doesn't exist yet (ESPHome searches parent directories, so one file covers every installation):

```bash
cp secrets.yaml.example secrets.yaml
# edit secrets.yaml with your WiFi credentials and keys
```

### 6. Flash

```bash
esphome run myhouse/open-air-mini.yaml
esphome run myhouse/valve-1.yaml
# repeat for each valve
```

See [FLASHING.md](FLASHING.md) for more detail.
