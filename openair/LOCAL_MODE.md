# Local Mode — How it works today

## Overview

Local Mode is a fallback/standalone control system for the ventilation setup. It allows the fan and valves to operate **without Home Assistant**. It activates when:
- The HA API connection is lost, **or**
- The "Local Mode" toggle switch is turned on manually

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  OpenAIR Controller (open-air-mini-garage)             │
│  ESP32 + Duco Silent fan (PWM on GPIO15)             │
│  Polls valves via HTTP every 60s                     │
│  Sets fan speed based on WORST reading across valves │
└────────────┬─────────────────────────────────────────┘
             │ HTTP GET /sensor/CO2
             │ HTTP GET /sensor/Humidity
             │
    ┌────────┼────────┬────────┬────────┬────────┐
    ▼        ▼        ▼        ▼        ▼        │
 Valve 1  Valve 2  Valve 3  Valve 4  Valve 5    │
 (ESP32)  (ESP32)  (ESP32)  (ESP32)  (ESP32)    │
```

## Fan control (openair controller)

Every 60 seconds, the openair controller:

1. Resets `local_worst_co2` and `local_worst_humidity` to 0
2. Polls all 5 valves via HTTP (10 requests: CO2 + humidity per valve)
3. Keeps the maximum (worst) value for each metric
4. Sets fan speed based on thresholds:

| Condition | Fan speed |
|---|---|
| CO2 > 1500 ppm **or** humidity > 75% | **High (70%)** |
| CO2 > 900 ppm **or** humidity > 65% | **Medium (40%)** |
| Below all thresholds | **Low (15%)** |

The JSON parsing is done in `local_mode_helpers.h` — it extracts the `"value"` field from the ESPHome web server JSON response.

## Valve control (each valve independently)

Each valve runs its own local mode logic every 60 seconds:

1. Reads its **own** CO2 and humidity sensors (no HTTP — local I2C)
2. Sets valve position based on the same thresholds:

| Condition | Valve position |
|---|---|
| CO2 > 1500 ppm **or** humidity > 75% | **100% open** |
| CO2 > 900 ppm **or** humidity > 65% | **50% open** |
| Below all thresholds | **Closed (0%)** |

Valve positioning uses a 101-entry lookup table that maps 0-100% to stepper motor steps (0-525), accounting for the non-linear relationship between valve position and airflow.

## What's missing / limitations

### 1. Fan and valves don't coordinate
The fan sets its speed based on the worst reading, and each valve sets its own position based on its own reading — but there's **no feedback loop**. The fan doesn't know which valves are open, and valves don't know the fan speed. This means:
- If only 1 room needs ventilation, all the fan pressure goes through that valve + any leakage through "closed" valves
- If 4 rooms need ventilation simultaneously, the fan speed may be the same as for 1 room, but airflow per room is quartered

### 2. No proportional/continuous control
Only 3 discrete levels (off/half/full for valves, 15/40/70% for fan). No smooth ramping between sensor values.

### 3. No flow rate awareness
The system controls RPM/PWM percentage, not actual airflow (m³/h). Fan speed doesn't translate linearly to airflow — it depends on how many valves are open and duct resistance.

### 4. Threshold-only, no hysteresis on CO2
Humidity control in `open-air-mini-huis.yaml` has a 20-minute hold timer to prevent cycling. The openair local mode has no such hysteresis — it can oscillate between levels every 60 seconds if readings hover around a threshold.

### 6. Valve hunting near setpoint
When CO2 hovers near the target (e.g. 600 ppm), demand flickers between 0 and a tiny positive value. The valve position formula computes `ratio = room_demand / fan_demand` — when both are near zero, this division is numerically unstable and valves oscillate between fully open and minimum every cycle. This was discovered via the simulator.

**Fix:** apply a dead band. When `fan_demand < 5%`, skip the ratio calculation and open all valves fully. This distributes air evenly when there is no meaningful demand signal, and eliminates hunting. Implemented in `local_mode_valve.yaml` and configurable via `dead_band` in `local_mode_settings.yaml`.

### 5. No error resilience for unreachable valves
If a valve is unreachable (HTTP timeout/error), `update_worst_value` silently ignores it. This means a permanently unreachable valve is treated as "everything is fine" (CO2=0) rather than triggering a safe fallback.

---

# Suggested improvements

## A. Flow-rate based control (future)

This aligns with the idea shared in the community: **control airflow (m³/h) instead of fan speed (%)**. For now we assume equal flow capacity across all valves — the demand-based valve positioning should naturally resolve imbalances through backpressure (a room with high CO2 opens its valve wide, getting more of the available airflow). Per-valve flow calibration can be added later if needed.

## B. Design direction: split control with fan speed as shared signal

Core idea: the **fan controller computes and sets fan speed** based on aggregate sensor readings. Each **valve reads the fan speed** from the openair controller and, combined with its own local sensor readings, **decides its own position**. Communication is all HTTP GET — no pushes needed.

### Design principles

1. **Fan speed is the shared signal** — the fan controller exposes its speed via the web server (`/fan/Open AIR Mini`). Valves poll this to understand overall system demand.
2. **Valves decide locally** — each valve knows its own CO2/humidity and the current fan speed. High local demand + high fan speed → open wide. Low local demand → close down to redirect airflow to needier rooms.
3. **Valves stay slightly open** (configurable minimum, e.g. 5-10%) so sensors always read fresh air
4. **Continuous demand curve** — no discrete levels, smooth mapping from sensor readings to demand
5. **Smoothing over hysteresis** — EMA on the demand signal to prevent jitter from sensor noise
6. **Shared settings file** — all tuning parameters live in `local_mode_settings.yaml`, included by both openair and valve configs

### Settings file (`local_mode_settings.yaml`)

```yaml
substitutions:
  # Sensor targets (below these = no demand)
  co2_target: "600"        # ppm - outdoor baseline
  co2_max: "1500"          # ppm - full demand
  humidity_target: "60"    # % - comfortable baseline
  humidity_max: "75"       # % - full demand

  # Fan speed range
  fan_speed_min: "15"      # % - always-on minimum
  fan_speed_max: "70"      # % - maximum speed

  # Valve position range
  valve_pos_min: "0.05"    # keep slightly open for sensor freshness
  valve_pos_max: "1.0"     # fully open

  # Dead band: below this fan demand, all valves open fully (prevents hunting near setpoint)
  dead_band: "0.05"

  # Smoothing (EMA alpha: 0=ignore new, 1=no smoothing)
  smoothing_alpha: "0.7"

  # Polling interval
  poll_interval: "60s"

  # Fan controller hostname (for valves to poll)
  fan_host: "open-air-mini-garage.local"

  # Unreachable device handling
  fail_count_warn: "3"    # after N failures: assume moderate demand
  fail_count_max: "10"    # after N failures: assume full demand
```

### Fan logic (openair controller)

Every poll cycle, the openair controller:

1. **Polls CO2 + humidity** from each valve via HTTP (already works)
2. **Computes per-valve demand** centrally:

```cpp
// Per-valve demand based on distance from target
float co2_demand = clamp((co2 - CO2_TARGET) / (CO2_MAX - CO2_TARGET), 0.0f, 1.0f);
float hum_demand = clamp((hum - HUM_TARGET) / (HUM_MAX - HUM_TARGET), 0.0f, 1.0f);
float demand = max(co2_demand, hum_demand);
```

3. **Computes fan speed** from aggregate demand:

```cpp
float total_demand = sum of all valve demands;
float max_demand = max of all valve demands;

// Fan must at least serve the neediest room, scale up for multiple
float fan_factor = max(max_demand, total_demand / num_valves);
int speed = FAN_SPEED_MIN + (int)(fan_factor * (FAN_SPEED_MAX - FAN_SPEED_MIN));
```

4. **Applies EMA smoothing** to fan speed to prevent jitter

### Valve logic (each valve independently)

Every poll cycle, each valve:

1. **Reads own CO2 + humidity** (local I2C, no HTTP)
2. **Reads current fan speed** from openair controller via HTTP GET `/fan/Open AIR Mini`
3. **Computes own demand** using the same formula as the fan:

```cpp
float co2_demand = clamp((co2 - CO2_TARGET) / (CO2_MAX - CO2_TARGET), 0.0f, 1.0f);
float hum_demand = clamp((hum - HUM_TARGET) / (HUM_MAX - HUM_TARGET), 0.0f, 1.0f);
float demand = max(co2_demand, hum_demand);
```

4. **Computes valve position** using fan speed to coordinate with other rooms:

```cpp
// Normalize fan speed to a demand value (0-1)
float fan_demand = clamp((fan_speed - FAN_SPEED_MIN) / (FAN_SPEED_MAX - FAN_SPEED_MIN), 0.0f, 1.0f);

if (fan_demand < DEAD_BAND) {
  // Dead band: no meaningful demand signal — open all valves fully.
  // Prevents hunting when CO2/humidity hover near the target (both demand
  // and fan_demand near zero → ratio = 0/0 → unstable).
  position = VALVE_POS_MAX;
} else {
  // Ratio: how much of the fan's effort is for this room?
  // If this room is driving the fan → ratio ≈ 1.0 → stay open
  // If another room is driving the fan → ratio < 1.0 → close down
  float ratio = clamp(demand / fan_demand, 0.0f, 1.0f);
  position = VALVE_POS_MIN + ratio * (VALVE_POS_MAX - VALVE_POS_MIN);
}
```

This naturally balances airflow: rooms with high demand stay wide open while rooms that don't need the air close down, redirecting flow where it's needed. Assuming linearity throughout.

### Handle unreachable fan controller

If a valve can't reach the fan controller:
- Continue using local sensor readings to set position (already self-sufficient)
- Log a warning for diagnostics

### Handle unreachable valves (fan side)

If the fan can't reach a valve:
- After 3 consecutive failures, treat as demand=0.5 (moderate ventilation, fail-safe)
- After 10 consecutive failures, treat as demand=1.0 (assume worst case)
- Log warnings visible in diagnostics

## C. Suggested priority for next steps

1. **Create `local_mode_settings.yaml`** — extract all magic numbers into one shared file
2. **Continuous fan control** — replace 3-level fan logic with continuous curve using settings
3. **Continuous valve control** — valves read own sensors + fan speed, compute position using demand/fan_demand ratio
4. **EMA smoothing** — smooth demand signal to prevent jitter
5. **Unreachable device handling** — fail-safe for unreachable valves/fan
6. **Flow-rate based control** — the end goal: control in m³/h instead of %, requires characterizing the fan curve
