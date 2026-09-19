#pragma once
// 跟主板 esp32-bringup 的 telemetry_config.h / telemetry_local.h 同一套模式：
// 真正的帳密放在 cam_wifi_local.h（不進 git），這裡只放預設值/佔位字串。
#if __has_include("cam_wifi_local.h")
#include "cam_wifi_local.h"
#endif

#ifndef CAM_WIFI_SSID
#define CAM_WIFI_SSID "your-hotspot"
#endif
#ifndef CAM_WIFI_PASSWORD
#define CAM_WIFI_PASSWORD "your-password"
#endif
