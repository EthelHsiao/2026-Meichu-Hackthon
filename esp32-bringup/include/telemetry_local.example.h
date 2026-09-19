#pragma once
// Copy to telemetry_local.h only if you need to override the defaults.
// 0: PC joins ESP32-Companion; 1: ESP32 joins an existing 2.4 GHz hotspot.
#define TELEMETRY_USE_STA 0
#define TELEMETRY_STA_SSID "your-hotspot"
#define TELEMETRY_STA_PASSWORD "your-password"
// Disable disconnected sensors: a floating ADC input isn't a valid FSR reading.
#define TELEMETRY_FSR_ENABLED 1
#define TELEMETRY_IMU_ENABLED 1
#define TELEMETRY_PERIOD_MS 50
