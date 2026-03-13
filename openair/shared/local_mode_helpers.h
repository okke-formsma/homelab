#pragma once

#include <algorithm>
#include <cmath>

// Parse the "value" field from an ESPHome web server JSON response.
// Returns NAN on failure.
inline float parse_sensor_value(const std::string &body, int status_code) {
  if (status_code != 200) {
    ESP_LOGW("local_mode", "HTTP error %d, body: %s", status_code, body.c_str());
    return NAN;
  }
  auto p = body.find("\"value\":");
  if (p == std::string::npos) {
    ESP_LOGW("local_mode", "No 'value' field in response: %s", body.c_str());
    return NAN;
  }
  float v = atof(body.c_str() + p + 8);
  ESP_LOGD("local_mode", "Extracted: %.2f", v);
  return v;
}

// Compute demand (0-1) from a sensor value given target and max thresholds.
inline float compute_demand(float value, float target, float max_val) {
  if (std::isnan(value)) return 0.0f;
  return std::max(0.0f, std::min(1.0f, (value - target) / (max_val - target)));
}

// Apply EMA smoothing: result = alpha * new_value + (1 - alpha) * old_value
inline float ema(float old_value, float new_value, float alpha) {
  if (std::isnan(old_value)) return new_value;
  return alpha * new_value + (1.0f - alpha) * old_value;
}
