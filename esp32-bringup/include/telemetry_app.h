#pragma once
#include <WiFi.h>
#include <WebServer.h>
#include <WebSocketsServer.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <math.h>
#include "telemetry_config.h"
#include "telemetry_dashboard.h"

static WebServer telemetryHttp(80);
static WebSocketsServer telemetryWs(WS_PORT);
static Adafruit_MPU6050 telemetryMpu;
static bool imuReady = false;
static bool imuSampleOk = false;
static bool imuRawFallback = false;  // Adafruit 驅動 begin() 失敗，但晶片本身有回應（跟 Stage 4 診斷出的狀況一樣）

// 跟 Stage 4（s4_imu）診斷用的是同一組暫存器位址，Invensense 這系列
// （MPU6050/6500/9250/9255...）不管型號，暫存器位置幾乎都相容：
//   0x6B PWR_MGMT_1   開機預設是 sleep 模式，要先清掉 sleep bit 感測器才會真的取樣
//   0x1C ACCEL_CONFIG 設 ±8g，量測範圍跟 Adafruit 驅動原本設的一致
//   0x1B GYRO_CONFIG  設 ±500 dps，同上
//   0x3B..0x48        14 byte 原始輸出：accel xyz / temp / gyro xyz
// 這顆晶片的 WHO_AM_I 讀到 0x74，不是 Adafruit_MPU6050 認得的型號，所以
// 換成直接操作暫存器；量測範圍設定跟換算比例沿用標準 Invensense 規格，
// 是 [CANDIDATE]——這顆晶片是不是真的照這個規格沒有另外驗證過，數字要
// 拿真實角度/靜置重力去對一次才能確認準不準。
static bool imuRawWrite(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(IMU_I2C_ADDR);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

static bool imuRawWake() {
  bool ok = true;
  ok &= imuRawWrite(0x6B, 0x01);  // PWR_MGMT_1：清 sleep bit，clock source 用 X 軸陀螺儀
  ok &= imuRawWrite(0x1C, 0x10);  // ACCEL_CONFIG：AFS_SEL=10 → ±8g
  ok &= imuRawWrite(0x1B, 0x08);  // GYRO_CONFIG：FS_SEL=01 → ±500 dps
  return ok;
}

static bool imuRawRead(int16_t out[7]) {
  Wire.beginTransmission(IMU_I2C_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;
  const uint8_t n = Wire.requestFrom((uint8_t)IMU_I2C_ADDR, (uint8_t)14);
  if (n != 14) return false;
  for (uint8_t i = 0; i < 7; i++) {
    const uint8_t hi = Wire.read();
    const uint8_t lo = Wire.read();
    out[i] = (int16_t)((hi << 8) | lo);
  }
  return true;
}

static String latestSample;
static char deviceId[24];
static char bootId[9];
static uint32_t sampleSeq = 0;

static void sampleSensors() {
  const uint32_t sampledAt = millis();
  char fsr[48];
  if (TELEMETRY_FSR_ENABLED) {
    snprintf(fsr, sizeof(fsr), "[%d,%d]", analogRead(PIN_FSR1_SENSE), analogRead(PIN_FSR2_SENSE));
  } else {
    strcpy(fsr, "null");
  }
  char imu[320];
  imuSampleOk = false;
  if (imuReady) {
    // Probe each sample so unplugging the IMU doesn't silently emit stale values.
    Wire.beginTransmission(IMU_I2C_ADDR);
    if (Wire.endTransmission() == 0) {
      sensors_event_t a{}, g{}, t{};
      imuSampleOk = telemetryMpu.getEvent(&a, &g, &t)
        && isfinite(a.acceleration.x) && isfinite(a.acceleration.y) && isfinite(a.acceleration.z)
        && isfinite(g.gyro.x) && isfinite(g.gyro.y) && isfinite(g.gyro.z) && isfinite(t.temperature);
      if (imuSampleOk) {
        snprintf(imu, sizeof(imu),
          "{\"ok\":true,\"status\":\"ok\",\"accel_m_s2\":[%.4f,%.4f,%.4f],"
          "\"gyro_rad_s\":[%.4f,%.4f,%.4f],\"temperature_c\":%.2f}",
          a.acceleration.x, a.acceleration.y, a.acceleration.z,
          g.gyro.x, g.gyro.y, g.gyro.z, t.temperature);
      }
    }
  } else if (imuRawFallback) {
    int16_t raw[7];
    if (imuRawRead(raw)) {
      // ±8g -> 4096 LSB/g；±500dps -> 65.5 LSB/(deg/s)；溫度公式是 Invensense 標準換算。
      const float ax = raw[0] / 4096.0f * 9.80665f;
      const float ay = raw[1] / 4096.0f * 9.80665f;
      const float az = raw[2] / 4096.0f * 9.80665f;
      const float gx = raw[4] / 65.5f * (float)M_PI / 180.0f;
      const float gy = raw[5] / 65.5f * (float)M_PI / 180.0f;
      const float gz = raw[6] / 65.5f * (float)M_PI / 180.0f;
      const float temp = raw[3] / 340.0f + 36.53f;
      imuSampleOk = isfinite(ax) && isfinite(ay) && isfinite(az) && isfinite(gx) && isfinite(gy) && isfinite(gz);
      if (imuSampleOk) {
        snprintf(imu, sizeof(imu),
          "{\"ok\":true,\"status\":\"raw_fallback\",\"accel_m_s2\":[%.4f,%.4f,%.4f],"
          "\"gyro_rad_s\":[%.4f,%.4f,%.4f],\"temperature_c\":%.2f}",
          ax, ay, az, gx, gy, gz, temp);
      }
    }
  }
  if (!imuSampleOk) {
    snprintf(imu, sizeof(imu), "{\"ok\":false,\"status\":\"%s\",\"accel_m_s2\":null,"
      "\"gyro_rad_s\":null,\"temperature_c\":null}",
      !TELEMETRY_IMU_ENABLED ? "disabled" : (imuReady || imuRawFallback) ? "read_failed" : "not_found");
  }
  char packet[768];
  snprintf(packet, sizeof(packet),
    "{\"schema_version\":1,\"type\":\"telemetry\",\"device_id\":\"%s\",\"boot_id\":\"%s\","
    "\"seq\":%lu,\"uptime_ms\":%lu,\"sample_period_ms\":%u,"
    "\"fsr\":{\"enabled\":%s,\"raw\":%s},\"imu\":%s}",
    deviceId, bootId, (unsigned long)++sampleSeq, (unsigned long)sampledAt,
    (unsigned)TELEMETRY_PERIOD_MS, TELEMETRY_FSR_ENABLED ? "true" : "false", fsr, imu);
  latestSample = packet;
}

static void telemetryEvent(uint8_t client, WStype_t type, uint8_t *payload, size_t length) {
  if (type == WStype_CONNECTED) {
    // The library reports the requested URL as the connected event payload.
    const char *path = "/api/v1/stream";
    if (length != strlen(path) || memcmp(payload, path, length) != 0) {
      telemetryWs.disconnect(client);
      return;
    }
    telemetryWs.sendTXT(client, latestSample);
    Serial.printf("WS client %u connected\n", client);
  } else if (type == WStype_DISCONNECTED) {
    Serial.printf("WS client %u disconnected\n", client);
  } else if (type == WStype_TEXT) {
    // Bound and compare by length: received payload needn't be null-terminated.
    if (length == 4 && memcmp(payload, "ping", 4) == 0) {
      telemetryWs.sendTXT(client, "{\"schema_version\":1,\"type\":\"pong\"}");
    } else {
      telemetryWs.sendTXT(client, "{\"schema_version\":1,\"type\":\"error\",\"code\":\"unsupported_command\"}");
    }
  }
}

void setup() {
  Serial.begin(MONITOR_SPEED);
  delay(1200);
  Serial.println("\nStage 9: real FSR + MPU6050 / HTTP + WebSocket");
  snprintf(deviceId, sizeof(deviceId), "esp32-%012llx", ESP.getEfuseMac());
  snprintf(bootId, sizeof(bootId), "%08lx", (unsigned long)esp_random());
  if (TELEMETRY_FSR_ENABLED) {
    analogReadResolution(ADC_RESOLUTION_BITS);
    analogSetPinAttenuation(PIN_FSR1_SENSE, ADC_ATTEN);
    analogSetPinAttenuation(PIN_FSR2_SENSE, ADC_ATTEN);
  }
  if (TELEMETRY_IMU_ENABLED) {
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, I2C_FREQ_HZ);
    Wire.setTimeOut(20);
    imuReady = telemetryMpu.begin(IMU_I2C_ADDR, &Wire);
    if (imuReady) {
      telemetryMpu.setAccelerometerRange(MPU6050_RANGE_8_G);
      telemetryMpu.setGyroRange(MPU6050_RANGE_500_DEG);
      telemetryMpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
    } else {
      // 跟 s4_imu 診斷到的狀況一樣：WHO_AM_I 不是 Adafruit 認得的型號，
      // 改成直接操作暫存器（喚醒 + 設定量測範圍），繞過驅動的型號檢查。
      imuRawFallback = imuRawWake();
      Serial.printf("IMU raw fallback: %d\n", imuRawFallback);
    }
  }
  Serial.printf("FSR enabled: %d; IMU initialized: %d\n", TELEMETRY_FSR_ENABLED, imuReady);

  if (TELEMETRY_USE_STA) {
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(TELEMETRY_STA_SSID, TELEMETRY_STA_PASSWORD);
    Serial.println("Joining configured hotspot; IP will print when connected.");
  } else {
    WiFi.mode(WIFI_AP);
    if (!WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD)) {
      Serial.println("ERROR: SoftAP startup failed");
    }
    Serial.printf("Join WiFi: %s\nDashboard: http://%s/\n", WIFI_AP_SSID, WiFi.softAPIP().toString().c_str());
  }
  sampleSensors();
  telemetryHttp.on("/", HTTP_GET, []() {
    String page = FPSTR(TELEMETRY_DASHBOARD);
    page.replace("__WS_PORT__", String(WS_PORT));
    telemetryHttp.send(200, "text/html; charset=utf-8", page);
  });
  telemetryHttp.on("/api/v1/health", HTTP_GET, []() {
    String body = "{\"schema_version\":1,\"ok\":true,\"device_id\":\"" + String(deviceId)
      + "\",\"wifi_mode\":\"" + (TELEMETRY_USE_STA ? "sta" : "ap")
      + "\",\"imu_ok\":" + (imuSampleOk ? "true" : "false") + "}";
    telemetryHttp.sendHeader("Cache-Control", "no-store");
    telemetryHttp.send(200, "application/json", body);
  });
  telemetryHttp.on("/api/v1/telemetry", HTTP_GET, []() {
    telemetryHttp.sendHeader("Cache-Control", "no-store");
    telemetryHttp.send(200, "application/json", latestSample);
  });
  telemetryHttp.onNotFound([]() {
    telemetryHttp.send(404, "application/json", "{\"type\":\"error\",\"code\":\"not_found\"}");
  });
  telemetryHttp.begin();
  telemetryWs.begin();
  telemetryWs.onEvent(telemetryEvent);
  telemetryWs.enableHeartbeat(15000, 3000, 2);
}

void loop() {
  telemetryHttp.handleClient();
  telemetryWs.loop();
  const uint32_t now = millis();
  static uint32_t lastSample = 0;
  if (now - lastSample >= TELEMETRY_PERIOD_MS) {
    lastSample = now;
    sampleSensors();
    telemetryWs.broadcastTXT(latestSample);
  }
  if (TELEMETRY_USE_STA) {
    static bool wasConnected = false;
    static uint32_t lastRetry = 0;
    const bool connected = WiFi.status() == WL_CONNECTED;
    if (connected && !wasConnected) Serial.printf("Dashboard: http://%s/\n", WiFi.localIP().toString().c_str());
    if (!connected && wasConnected) Serial.println("WiFi disconnected; retrying...");
    if (!connected && now - lastRetry >= 10000) {
      lastRetry = now;
      WiFi.reconnect();
    }
    wasConnected = connected;
  }
  delay(1);
}
