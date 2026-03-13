#pragma once

inline void update_worst_value(float &worst, const std::string &body, int status_code) {
  if (status_code != 200) {
    ESP_LOGW("local_mode", "HTTP error %d, body: %s", status_code, body.c_str());
    return;
  }
  ESP_LOGD("local_mode", "Response: %s", body.c_str());
  auto p = body.find("\"value\":");
  if (p == std::string::npos) {
    ESP_LOGW("local_mode", "No 'value' field in response: %s", body.c_str());
    return;
  }
  float v = atof(body.c_str() + p + 8);
  ESP_LOGD("local_mode", "Extracted: %.2f (current worst: %.2f)", v, worst);
  if (v > 0.0f && v > worst) {
    worst = v;
    ESP_LOGI("local_mode", "New worst: %.2f", v);
  }
}
