#pragma once

#include <algorithm>
#include <cmath>
#include <string>
#include "mdns.h"
#include "esp_http_client.h"

// Apply EMA smoothing: result = alpha * new_value + (1 - alpha) * old_value
inline float ema(float old_value, float new_value, float alpha) {
  if (std::isnan(old_value)) return new_value;
  return alpha * new_value + (1.0f - alpha) * old_value;
}

// Check if an mDNS (.local) hostname is reachable with a bounded timeout.
// Prevents the HTTP client from blocking on DNS for offline hosts, which
// triggers the ESP32 watchdog.
inline bool is_mdns_host_reachable(const char* hostname, uint32_t timeout_ms = 2000) {
    std::string host(hostname);
    auto pos = host.find(".local");
    if (pos != std::string::npos) host = host.substr(0, pos);

    esp_ip4_addr_t addr = {};
    esp_err_t err = mdns_query_a(host.c_str(), timeout_ms, &addr);
    if (err != ESP_OK) {
        ESP_LOGW("mdns", "Cannot resolve %s: %s", hostname, esp_err_to_name(err));
        return false;
    }
    ESP_LOGD("mdns", "Resolved %s to " IPSTR, hostname, IP2STR(&addr));
    return true;
}

// HTTP GET with mDNS pre-check. Returns response body, or "" on failure.
inline std::string http_get(const char* url, const char* hostname) {
    if (!is_mdns_host_reachable(hostname)) return "";

    esp_http_client_config_t config = {};
    config.url = url;
    config.timeout_ms = 3000;

    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) { ESP_LOGW("http", "Init failed: %s", url); return ""; }

    std::string result;
    esp_err_t err = esp_http_client_open(client, 0);
    if (err != ESP_OK) {
        ESP_LOGW("http", "Connect failed %s: %s", url, esp_err_to_name(err));
    } else {
        esp_http_client_fetch_headers(client);
        int status = esp_http_client_get_status_code(client);
        if (status != 200) {
            ESP_LOGW("http", "HTTP %d from %s", status, url);
        } else {
            char buf[512];
            int len = esp_http_client_read(client, buf, sizeof(buf) - 1);
            if (len > 0) { buf[len] = '\0'; result = buf; }
        }
    }
    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    return result;
}

// Extract a float from a JSON field like "value":1.23 — returns NAN on failure.
inline float parse_json_float(const std::string &body, const char* field) {
    auto p = body.find(field);
    if (p == std::string::npos) {
        ESP_LOGW("json", "No '%s' in: %s", field, body.c_str());
        return NAN;
    }
    return atof(body.c_str() + p + strlen(field));
}

// Poll a single valve's demand via HTTP. Returns NAN if disabled or unreachable.
inline float poll_valve_demand(const char* host) {
    if (std::string(host) == "0.0.0.0") return NAN;
    std::string url = std::string("http://") + host + "/sensor/Demand";
    ESP_LOGD("poll", "GET %s", url.c_str());
    std::string body = http_get(url.c_str(), host);
    if (body.empty()) return NAN;
    ESP_LOGD("poll", "Response: %s", body.c_str());
    return parse_json_float(body, "\"value\":");
}

// Poll the fan controller for its current speed. Returns NAN if unreachable.
inline float poll_fan_speed(const char* fan_host) {
    std::string url = std::string("http://") + fan_host + "/fan/Open%20AIR%20Mini";
    ESP_LOGD("poll", "GET %s", url.c_str());
    std::string body = http_get(url.c_str(), fan_host);
    if (body.empty()) {
        ESP_LOGW("poll", "Fan controller %s unreachable", fan_host);
        return NAN;
    }
    ESP_LOGD("poll", "Response: %s", body.c_str());
    return parse_json_float(body, "\"speed_level\":");
}
