#pragma once

// Optional local settings (ignored by Git). See telemetry_local.example.h.
#if __has_include("telemetry_local.h")
#include "telemetry_local.h"
#endif

#ifndef TELEMETRY_USE_STA
#define TELEMETRY_USE_STA 0
#endif
#ifndef TELEMETRY_STA_SSID
#define TELEMETRY_STA_SSID ""
#endif
#ifndef TELEMETRY_STA_PASSWORD
#define TELEMETRY_STA_PASSWORD ""
#endif
#ifndef TELEMETRY_FSR_ENABLED
#define TELEMETRY_FSR_ENABLED 1
#endif
#ifndef TELEMETRY_IMU_ENABLED
#define TELEMETRY_IMU_ENABLED 1
#endif
#ifndef TELEMETRY_PERIOD_MS
#define TELEMETRY_PERIOD_MS 50
#endif
static_assert(TELEMETRY_PERIOD_MS >= 20, "Use 50 Hz or less for bring-up");
