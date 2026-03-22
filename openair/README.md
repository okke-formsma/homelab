# Open-AIR — fan and valve control

**[▶ Open simulator](https://formsma.nl/homelab/openair/simulator.html)** — interactive tool to explore how the fan and valves respond to sensor readings.

Local Mode is a standalone control system that lets the fan and valves operate **without Home Assistant**. It activates when:
- The HA API connection is lost, **or**
- The "Local Mode" toggle switch is turned on manually

---

## Repository layout

```
openair/
  shared/          ← shared logic — never edit these
  garage/          ← garage installation (fan controller + 5 valves)
  huis/            ← huis installation (fan controller + 4 valves)
  example/         ← copy this to start a new installation
  secrets.yaml.example  ← template for per-install secrets.yaml
```

Each installation directory contains:

| File | Purpose |
|---|---|
| `config.yaml` | All user-configurable settings: `device_name`, `fan_host`, valve hostnames |
| `open-air-mini.yaml` | Fan controller: hardware config (no user edits needed) |
| `valve-N.yaml` | One file per valve: device name + hardware template |

---

## Setting up a new installation

### 0. Create a directory

```bash
mkdir myhouse
```

### 1. Secrets

Copy `secrets.yaml` into your installation directory (ESPHome only looks for it next to the config being compiled). If you want a single shared file, use a symlink from each install to the same secrets file.

```bash
cp secrets.yaml.example myhouse/secrets.yaml
# edit with your WiFi credentials and OTA password
```

### 2. Create `myhouse/config.yaml`

Copy from `example/config.yaml`. Fill in your device name and valve hostnames:

```yaml
packages:
  defaults: !include ../shared/local_mode_defaults.yaml
  settings: !include ../shared/local_mode_settings.yaml

substitutions:
  device_name: "open-air-mini-<yourname>"
  fan_host: "${device_name}.local"

  valve_1_host: "example-valve-1.local"
  valve_2_host: "example-valve-2.local"
  # Unused slots default to "0.0.0.0" in local_mode_fan.yaml — no need to list them
```

`fan_host` is automatically derived from `device_name`, so you only need to set the name once.

### 3. Create `myhouse/open-air-mini.yaml`

Copy from `example/fan-controller.yaml`. No modifications needed — it picks up all settings from `config.yaml` via the `packages` include at the top:

```yaml
packages:
  config: !include config.yaml
  local_mode: !include ../shared/local_mode_fan.yaml
# ...
```

### 4. Create `myhouse/valve-N.yaml` for each valve

Copy from `example/valve-1.yaml`. Fill in `devicename` and `upper_devicename`.
`fan_host` comes automatically from `config.yaml`.

```yaml
substitutions:
  devicename: example-valve-1
  upper_devicename: Example Valve 1

packages:
  config: !include config.yaml
  hardware: !include ../shared/Open_AIR_Valve_DIS_SCD40_SGP41.yaml

esphome:
  includes:
    - ../shared/local_mode_helpers.h
```

Repeat for each valve (e.g., valve-1 and valve-2), incrementing the number.

#### Choosing the hardware package

Pick the hardware include that matches your sensor set:
- `shared/Open_AIR_Valve_DIS_SHT4x.yaml`: SHT4x only — humidity, temperature. A dummy CO₂ sensor (NaN) is included so the local mode demand calculation works; demand is driven by humidity only.
- `shared/Open_AIR_Valve_DIS_SCD40.yaml`: SCD40 only — CO₂, humidity, temperature.
- `shared/Open_AIR_Valve_DIS_SCD40_SGP41.yaml`: SCD40 + SGP41 — CO₂, humidity, temperature, VOC index, NOx index.

Use the variant that matches the sensors present on the valve PCB. If you choose the wrong one, the build will fail or the extra sensors will read as unavailable.

### 5. Flash

```bash
esphome run myhouse/open-air-mini.yaml
esphome run myhouse/valve-1.yaml
esphome run myhouse/valve-2.yaml
# repeat for each valve
```

See [FLASHING.md](FLASHING.md) for more detail.

---

## Architecture

Each fan controller manages its own set of valves independently.

```
┌──────────────────────────────────────┐
│  open-air-mini-<yourname> (3 valves) │
│  Polls valves via HTTP every 60s     │
│  Exposes fan speed via web server    │
└──────────────┬───────────────────────┘
               ▼ GET /sensor/Demand
               |
     ┌─────────┼──────────┐
     ▲         ▲          ▲   GET /fan/Open AIR Mini
     |         |          |
┌──────────┐ ┌──────────┐ ┌──────────────┐
│ valve-1  │ │ valve-2  │ │ valve-3      │
│ SHT4x    │ │ SCD40    │ │ SCD40+SGP41  │
│ H/T      │ │ CO₂/H/T  │ │ CO₂/H/T/V/N  │
└──────────┘ └──────────┘ └──────────────┘
```

Unused valve slots in `local_mode_fan.yaml` default to `"0.0.0.0"`. Requests to that address fail immediately, return NAN, and are excluded from demand calculation — no special handling needed.

---

## How it works

### Shared settings (`shared/local_mode_settings.yaml`)

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
| `ki_scale` | 0.5 | Max demand added by a fully charged integral (0 = disable I term) |
| `integral_max` | 10 | Polls (minutes at full demand) to saturate the integral |
| `poll_interval` | 60s | How often to poll and recompute |

### Fan control (`shared/local_mode_fan.yaml`)

Every poll cycle, the fan controller:

1. **Polls PI demand** from all configured valves via HTTP (`/sensor/Demand`, one request per slot)
2. **Fan demand = max demand** across all reachable valves (the neediest room drives the fan); demand already includes the I term computed on each valve
4. **Applies EMA smoothing** to prevent jitter
5. **Sets fan speed**: `fan_speed_min + smoothed_demand × (fan_speed_max − fan_speed_min)`

Valves returning NAN (unreachable or sensor error) are excluded. The system keeps running on whatever valves are reachable — worst case at minimum fan speed.

The fan speed is exposed via the ESPHome web server at `/fan/Open AIR Mini`, which valves poll to coordinate.

### Valve control (`shared/local_mode_valve.yaml`)

Each valve runs independently every poll cycle:

1. **Reads own sensors** (CO₂ + humidity, or humidity-only for SHT4x valves) from local I2C
2. **Polls current fan speed** from the fan controller via HTTP GET
3. **Computes own PI demand** (0–1) — see below
4. **Applies EMA smoothing**
5. **Sets valve position** using the fan speed to coordinate with other rooms:

#### PI controller

Demand is computed as a proportional term (P) plus an integral term (I):

```
signed_error = max(
  (co2 − co2_target) / (co2_max − co2_target),
  (humidity − hum_target) / (hum_max − hum_target)
)

P = clamp(signed_error, 0, 1)

integral += signed_error          # accumulates when above target, drains when below
integral  = clamp(integral, 0, integral_max)
I_contribution = (integral / integral_max) × ki_scale

pi_demand = clamp(P + I_contribution, 0, 1)
```

The I term means a room that lingers just above the CO₂ target will gradually increase demand over time, pushing the fan harder. When the CO₂ finally drops below target, the integral drains and the fan "runs on" briefly before settling. Set `ki_scale: "0"` to revert to pure-P behaviour.

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

---

## Fault scenarios

- **Valve offline:** fan controller ignores its demand after request failure; fan demand is computed from reachable valves only.
- **All valves offline:** fan demand becomes 0 and the fan falls back to `fan_speed_min` (always-on minimum).
- **Wi‑Fi/router outage (fan + valves unreachable):** fan controller sees zero reachable valves and runs at `fan_speed_min`; valves can’t reach the fan controller and default to fully open.
- **Fan controller offline:** valves open fully as a safe default to distribute air to all rooms.
- **Home Assistant offline:** Local Mode activates automatically and continues local control.
- **Sensor error / NAN:** room demand becomes 0 and is excluded from fan demand.

---

## Assumptions and approximations

### Fan speed is driven by the single worst room
Fan demand equals the maximum demand across all valves. The fan runs at the same speed whether 1 room or 5 rooms need air at the same demand level. With more valves open, total system resistance drops and the fan delivers more total flow at the same speed — so the physics partially self-correct. But with 5 rooms all demanding, each gets roughly 1/5th the airflow compared to a single room, so CO2 clears slower. Given the Ducobox Silent's 400 m³/h capacity, even split across 5 rooms this is 80 m³/h per room at full speed, which is typically sufficient.

### Linearity assumption in valve coordination
The valve position formula (`ratio = demand / fan_demand`) assumes airflow through a valve scales linearly with its opening. The lookup table compensates for the non-linear valve mechanics (position → stepper steps), but the distribution of airflow across parallel ducts also depends on duct lengths, diameters, and bends. Without per-duct flow measurement, this is the best practical approximation.

### No flow rate awareness
The system controls PWM percentage, not actual airflow (m³/h). The fan curve (RPM → m³/h at different backpressures) is unknown and would require expensive measurement equipment to characterize.
