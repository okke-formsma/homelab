#pragma once

#include <algorithm>
#include <cmath>
#include <map>
#include <string>
#include "mdns.h"
#include "esp_http_client.h"

// Apply EMA smoothing: result = alpha * new_value + (1 - alpha) * old_value
inline float ema(float old_value, float new_value, float alpha) {
  if (std::isnan(old_value)) return new_value;
  return alpha * new_value + (1.0f - alpha) * old_value;
}

// Resolve an mDNS (.local) hostname to an IP string, with a bounded timeout.
// Result is cached permanently — IPs are assumed stable between reboots.
// Returns nullptr on failure.
inline const char* resolve_mdns_host(const char* hostname, uint32_t timeout_ms = 2000) {
    static std::map<std::string, std::string> cache;

    std::string key(hostname);
    auto it = cache.find(key);
    if (it != cache.end()) return it->second.c_str();

    std::string host(hostname);
    auto pos = host.find(".local");
    if (pos != std::string::npos) host = host.substr(0, pos);

    esp_ip4_addr_t addr = {};
    esp_err_t err = mdns_query_a(host.c_str(), timeout_ms, &addr);
    if (err != ESP_OK) {
        ESP_LOGW("mdns", "Cannot resolve %s: %s", hostname, esp_err_to_name(err));
        return nullptr;
    }
    char ip_str[16];
    snprintf(ip_str, sizeof(ip_str), IPSTR, IP2STR(&addr));
    cache[key] = ip_str;
    ESP_LOGI("mdns", "Resolved %s -> %s (cached)", hostname, ip_str);
    return cache[key].c_str();
}

// HTTP GET hostname/path. Resolves hostname via mDNS (cached) and connects by IP,
// avoiding a second DNS lookup in the HTTP client. Returns response body, or "" on failure.
inline std::string http_get(const char* hostname, const char* path) {
    const char* ip = resolve_mdns_host(hostname);
    if (!ip) return "";

    std::string url = std::string("http://") + ip + path;
    esp_http_client_config_t config = {};
    config.url = url.c_str();
    config.timeout_ms = 3000;

    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (!client) { ESP_LOGW("http", "Init failed: %s", url.c_str()); return ""; }

    std::string result;
    esp_err_t err = esp_http_client_open(client, 0);
    if (err != ESP_OK) {
        ESP_LOGW("http", "Connect failed %s: %s", url.c_str(), esp_err_to_name(err));
    } else {
        esp_http_client_fetch_headers(client);
        int status = esp_http_client_get_status_code(client);
        if (status != 200) {
            ESP_LOGW("http", "HTTP %d from %s", status, url.c_str());
        } else {
            char buf[512];
            int len = esp_http_client_read(client, buf, sizeof(buf) - 1);
            if (len >= (int)(sizeof(buf) - 1))
                ESP_LOGW("http", "Response truncated at %d bytes from %s", len, url.c_str());
            if (len > 0) { buf[len] = '\0'; result = buf; }
        }
    }
    esp_http_client_close(client);
    esp_http_client_cleanup(client);
    return result;
}

// Extract a float from JSON — field is the key string (with or without trailing ':').
// Skips any ':' and whitespace after the field before parsing. Returns NAN on failure.
inline float parse_json_float(const std::string &body, const char* field) {
    auto p = body.find(field);
    if (p == std::string::npos) {
        ESP_LOGW("json", "No '%s' in: %s", field, body.c_str());
        return NAN;
    }
    const char* s = body.c_str() + p + strlen(field);
    while (*s == ':' || *s == ' ' || *s == '\t') s++;
    if (*s == '\0') {
        ESP_LOGW("json", "No value after '%s' in: %s", field, body.c_str());
        return NAN;
    }
    return atof(s);
}

// Poll a single valve's demand via HTTP. Returns NAN if disabled or unreachable.
inline float poll_valve_demand(const char* host) {
    if (std::string(host) == "0.0.0.0") return NAN;
    ESP_LOGD("poll", "GET http://%s/sensor/Demand", host);
    std::string body = http_get(host, "/sensor/Demand");
    if (body.empty()) return NAN;
    ESP_LOGD("poll", "Response: %s", body.c_str());
    return parse_json_float(body, "\"value\":");
}

// Poll the fan controller for its current speed. Returns NAN if unreachable.
inline float poll_fan_speed(const char* fan_host) {
    ESP_LOGD("poll", "GET http://%s/fan/Open%%20AIR%%20Mini", fan_host);
    std::string body = http_get(fan_host, "/fan/Open%20AIR%20Mini");
    if (body.empty()) {
        ESP_LOGW("poll", "Fan controller %s unreachable", fan_host);
        return NAN;
    }
    ESP_LOGD("poll", "Response: %s", body.c_str());
    return parse_json_float(body, "\"speed_level\":");
}
