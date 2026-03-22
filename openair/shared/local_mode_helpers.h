#pragma once

#include <algorithm>
#include <cmath>
#include "mdns.h"

// Check if an mDNS (.local) hostname is reachable, with a bounded timeout.
// Returns true if the host resolves, false otherwise. This prevents the
// HTTP client from blocking indefinitely on DNS resolution for offline hosts,
// which would trigger the ESP32 watchdog and reboot the device.
inline bool is_mdns_host_reachable(const char* hostname, uint32_t timeout_ms = 2000) {
    std::string host(hostname);
    // Strip ".local" suffix — mdns_query_a expects just the hostname part
    auto pos = host.find(".local");
    if (pos != std::string::npos) {
        host = host.substr(0, pos);
    }

    esp_ip4_addr_t addr;
    addr.addr = 0;
    esp_err_t err = mdns_query_a(host.c_str(), timeout_ms, &addr);
    if (err != ESP_OK) {
        ESP_LOGW("mdns", "Cannot resolve %s (timeout %ums): %s",
                 hostname, timeout_ms, esp_err_to_name(err));
        return false;
    }
    ESP_LOGD("mdns", "Resolved %s to " IPSTR, hostname, IP2STR(&addr));
    return true;
}

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
