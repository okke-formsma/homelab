#pragma once

inline void update_worst_value(float &worst, const std::string &body, int status_code) {
  if (status_code != 200) return;
  auto p = body.find("\"value\":");
  if (p == std::string::npos) return;
  float v = atof(body.c_str() + p + 8);
  if (v > 0.0f && v > worst) worst = v;
}
