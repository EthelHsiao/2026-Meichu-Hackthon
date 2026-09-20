#pragma once
// ============================================================
//  companion_app.h — Stage 13（s13_companion）：把 Stage 5(LCD)/9(FSR+IMU+WS)/
//  10(蜂鳴器)/11(麥克風) 併成一份整合韌體，對應 docs/api.html §① 定案的
//  WebSocket 合約。
//
//  ⚠️ 這份整合程式碼還沒有實機驗證過（各個 Stage 個別驗證過，但合併成一份
//  build 之後有沒有資源衝突——尤其 WiFi 開啟後對 I2S 麥克風的已知限制、
//  SPI(LCD) 跟其他週邊搶頻寬——都還沒有實測。見計畫「這份設計不會解決的
//  問題」第 1、2 點。上線前務必照專案既有的 Stage 紀律，先個別功能都在這個
//  env 底下驗證一次。
//
//  上行（ESP32 -> AIPC，WS text/binary frame）：
//    telemetry（跟 Stage 9 格式相同）
//    {"t":"touch","kind":"double_tap","strength":1.0,"dur_ms":0}
//    binary frame：INMP441 mono int16 PCM
//  下行（AIPC -> ESP32，WS text frame）：
//    {"t":"say","expr":"...","text":"...","done":true}  {"t":"expr","expr":"..."}
//    {"t":"clear"}   台詞串流見 ai-pc-agent/sensing/esp32_ws_client.py 的 say_stream()
//    {"t":"buzz","pattern":"..."}
// ============================================================
#include <ArduinoJson.h>
#include <WiFi.h>
#include <ESPmDNS.h>
#include <WebServer.h>
#include <WebSocketsServer.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <math.h>
#include "telemetry_config.h"
#include "telemetry_dashboard.h"
// 臉的每幀時間比 Stage 5 慢一點：這支還要餵麥克風 I2S、每 50ms 送一次 telemetry，
// 把 SPI 頻寬跟 CPU 留給音訊。一幀要把 40KB 畫面推到 SPI（27MHz 約 12ms），
// 麥克風的 DMA 是 4 x 256 frame = 16kHz 下約 64ms，緩衝夠深、不會因此掉音訊。
#define LCD_FRAME_MS 40
#include "lcd_faces.h"
#include "mic_stream.h"

static WebServer companionHttp(80);
static WebSocketsServer companionWs(WS_PORT);
static Adafruit_MPU6050 companionMpu;
static bool companionImuReady = false;
static bool companionImuSampleOk = false;
static bool companionImuRawFallback = false;

// ---- IMU：跟 telemetry_app.h 完全相同的暫存器 fallback 邏輯（見該檔案註解）----
static bool companionImuRawWrite(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(IMU_I2C_ADDR);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

static bool companionImuRawWake() {
  bool ok = true;
  ok &= companionImuRawWrite(0x6B, 0x01);
  ok &= companionImuRawWrite(0x1C, 0x10);
  ok &= companionImuRawWrite(0x1B, 0x08);
  return ok;
}

static bool companionImuRawRead(int16_t out[7]) {
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

static String companionLatestSample;
static char companionDeviceId[24];
static char companionBootId[9];
static uint32_t companionSampleSeq = 0;

// ---- FSR1 雙擊偵測：在韌體本地判斷、只送離散事件，比照既有「捏/搖在 ESP32
// 本地判斷，只送事件」的原則。閾值 [CONFIRMED]：2026-09-20 拿 receive_telemetry.py
// 實測按壓 raw 值校準過。----
static const int FSR1_PRESS_THRESHOLD = 250;       // [CONFIRMED] 實測按下超過 250
static const uint32_t FSR1_DEBOUNCE_MS = 60;        // 同一次按壓的抖動不要算成兩下
static const uint32_t FSR1_DOUBLE_TAP_WINDOW_MS = 600;

static bool s_fsr1Pressed = false;
static uint32_t s_fsr1LastEdgeMs = 0;
static uint32_t s_fsr1FirstTapMs = 0;
static uint8_t s_fsr1TapCount = 0;

static bool fsr1DetectDoubleTap(int raw, uint32_t now) {
  const bool pressed = raw > FSR1_PRESS_THRESHOLD;
  bool doubleTap = false;
  if (pressed && !s_fsr1Pressed && (now - s_fsr1LastEdgeMs) > FSR1_DEBOUNCE_MS) {
    s_fsr1LastEdgeMs = now;
    if (s_fsr1TapCount > 0 && (now - s_fsr1FirstTapMs) > FSR1_DOUBLE_TAP_WINDOW_MS) {
      s_fsr1TapCount = 0;  // 上一下拍太久以前了，不算數，當作新的第一下
    }
    if (s_fsr1TapCount == 0) s_fsr1FirstTapMs = now;
    s_fsr1TapCount++;
    if (s_fsr1TapCount >= 2) {
      doubleTap = true;
      s_fsr1TapCount = 0;
    }
  }
  s_fsr1Pressed = pressed;
  return doubleTap;
}

// ---- 蜂鳴器：沿用 Stage 10 驗證過的 tone()/noTone() 做法 ----
static void companionBuzzerTone(uint32_t freqHz, uint32_t durationMs) {
  tone(PIN_BUZZER, freqHz, durationMs);
  delay(durationMs + 20);  // 跟 Stage 10 一致：短暫阻塞，讓音符之間聽得出斷開
  noTone(PIN_BUZZER);
}

// pattern 由 AIPC 端指定，這裡只認得下面兩種、其他字串安全 fallback 成 "chirp"，
// 不會因為打錯字讓韌體卡住或斷線。
static void companionPlayBuzzPattern(const char *pattern) {
  if (pattern != nullptr && strcmp(pattern, "confirm") == 0) {
    companionBuzzerTone(660, 80);
    companionBuzzerTone(880, 100);
  } else {
    companionBuzzerTone(880, 60);
  }
}

// ---- 下行指令：{"t":"say"/"expr"/"buzz", ...}，見檔頭合約 ----
static void companionHandleDownlink(const uint8_t *payload, size_t length) {
  StaticJsonDocument<512> doc;   // 40 個中文字的 say 約 150 byte，256 太緊
  if (deserializeJson(doc, payload, length) != DeserializationError::Ok) return;  // 不是合法 JSON，安靜忽略
  const char *t = doc["t"];
  if (t == nullptr) return;
  if (strcmp(t, "expr") == 0) {
    const char *expr = doc["expr"];
    if (expr != nullptr && !lcdSetMoodByName(expr)) Serial.printf("未知表情：%s\n", expr);
  } else if (strcmp(t, "say") == 0) {
    const char *text = doc["text"];
    // expr 只跟著串流的第一段來；輪到這句開始顯示時才換表情
    if (text != nullptr) lcdSay(String(text), doc["done"] | true, doc["expr"]);
  } else if (strcmp(t, "clear") == 0) {
    lcdClearText();
  } else if (strcmp(t, "buzz") == 0) {
    companionPlayBuzzPattern(doc["pattern"]);
  }
}

// mDNS：STA/熱點模式下 IP 是 DHCP 動態給的，每次開機、每次重連都可能不一樣；
// 加了之後同一個熱點下的裝置可以固定用 esp32-companion.local 連過來，不用每次
// 開機都去 Serial Monitor 查 IP 再手動改 AIPC 那邊的設定。只在第一次真的拿到
// IP 時啟動一次（用 s_mdnsStarted 擋），避免斷線重連時重複呼叫；已知限制：如果
// 熱點重連後配到不同的 IP，這個 mDNS library 沒有內建「重新綁定」，理論上仍可能
// 廣播到舊 IP，這點還沒有實機驗證過，重連情境如果遇到連不到再回報。手機熱點/多數
// 路由器都支援 mDNS；AIPC 電腦連不到 .local 網址通常是還沒裝 avahi-daemon
// （Ubuntu：sudo apt install avahi-daemon libnss-mdns），退回用印出的實際 IP 一樣能連。
static bool s_mdnsStarted = false;
static void companionMdnsStart() {
  if (s_mdnsStarted) return;
  if (MDNS.begin("esp32-companion")) {
    MDNS.addService("http", "tcp", 80);
    MDNS.addService("ws", "tcp", WS_PORT);
    Serial.println("mDNS 就緒：http://esp32-companion.local/  ws://esp32-companion.local:81/api/v1/stream");
    s_mdnsStarted = true;
  } else {
    Serial.println("mDNS 啟動失敗（不影響用 IP 直接連）");
  }
}

static void companionSampleSensors() {
  const uint32_t sampledAt = millis();
  char fsr[48];
  int fsr1Raw = 0, fsr2Raw = 0;
  if (TELEMETRY_FSR_ENABLED) {
    fsr1Raw = analogRead(PIN_FSR1_SENSE);
    fsr2Raw = analogRead(PIN_FSR2_SENSE);
    snprintf(fsr, sizeof(fsr), "[%d,%d]", fsr1Raw, fsr2Raw);
  } else {
    strcpy(fsr, "null");
  }

  if (TELEMETRY_FSR_ENABLED && fsr1DetectDoubleTap(fsr1Raw, sampledAt)) {
    companionWs.broadcastTXT("{\"t\":\"touch\",\"kind\":\"double_tap\",\"strength\":1.0,\"dur_ms\":0}");
  }

  char imu[320];
  companionImuSampleOk = false;
  if (companionImuReady) {
    Wire.beginTransmission(IMU_I2C_ADDR);
    if (Wire.endTransmission() == 0) {
      sensors_event_t a{}, g{}, tmp{};
      companionImuSampleOk = companionMpu.getEvent(&a, &g, &tmp)
        && isfinite(a.acceleration.x) && isfinite(a.acceleration.y) && isfinite(a.acceleration.z)
        && isfinite(g.gyro.x) && isfinite(g.gyro.y) && isfinite(g.gyro.z) && isfinite(tmp.temperature);
      if (companionImuSampleOk) {
        snprintf(imu, sizeof(imu),
          "{\"ok\":true,\"status\":\"ok\",\"accel_m_s2\":[%.4f,%.4f,%.4f],"
          "\"gyro_rad_s\":[%.4f,%.4f,%.4f],\"temperature_c\":%.2f}",
          a.acceleration.x, a.acceleration.y, a.acceleration.z,
          g.gyro.x, g.gyro.y, g.gyro.z, tmp.temperature);
      }
    }
  } else if (companionImuRawFallback) {
    int16_t raw[7];
    if (companionImuRawRead(raw)) {
      const float ax = raw[0] / 4096.0f * 9.80665f;
      const float ay = raw[1] / 4096.0f * 9.80665f;
      const float az = raw[2] / 4096.0f * 9.80665f;
      const float gx = raw[4] / 65.5f * (float)M_PI / 180.0f;
      const float gy = raw[5] / 65.5f * (float)M_PI / 180.0f;
      const float gz = raw[6] / 65.5f * (float)M_PI / 180.0f;
      const float temp = raw[3] / 340.0f + 36.53f;
      companionImuSampleOk = isfinite(ax) && isfinite(ay) && isfinite(az) && isfinite(gx) && isfinite(gy) && isfinite(gz);
      if (companionImuSampleOk) {
        snprintf(imu, sizeof(imu),
          "{\"ok\":true,\"status\":\"raw_fallback\",\"accel_m_s2\":[%.4f,%.4f,%.4f],"
          "\"gyro_rad_s\":[%.4f,%.4f,%.4f],\"temperature_c\":%.2f}",
          ax, ay, az, gx, gy, gz, temp);
      }
    }
  }
  if (!companionImuSampleOk) {
    snprintf(imu, sizeof(imu), "{\"ok\":false,\"status\":\"%s\",\"accel_m_s2\":null,"
      "\"gyro_rad_s\":null,\"temperature_c\":null}",
      !TELEMETRY_IMU_ENABLED ? "disabled" : (companionImuReady || companionImuRawFallback) ? "read_failed" : "not_found");
  }
  char packet[768];
  snprintf(packet, sizeof(packet),
    "{\"schema_version\":1,\"type\":\"telemetry\",\"device_id\":\"%s\",\"boot_id\":\"%s\","
    "\"seq\":%lu,\"uptime_ms\":%lu,\"sample_period_ms\":%u,"
    "\"fsr\":{\"enabled\":%s,\"raw\":%s},\"imu\":%s}",
    companionDeviceId, companionBootId, (unsigned long)++companionSampleSeq, (unsigned long)sampledAt,
    (unsigned)TELEMETRY_PERIOD_MS, TELEMETRY_FSR_ENABLED ? "true" : "false", fsr, imu);
  companionLatestSample = packet;
}

static void companionWsEvent(uint8_t client, WStype_t type, uint8_t *payload, size_t length) {
  if (type == WStype_CONNECTED) {
    const char *path = "/api/v1/stream";
    if (length != strlen(path) || memcmp(payload, path, length) != 0) {
      companionWs.disconnect(client);
      return;
    }
    companionWs.sendTXT(client, companionLatestSample);
    Serial.printf("WS client %u connected\n", client);
  } else if (type == WStype_DISCONNECTED) {
    Serial.printf("WS client %u disconnected\n", client);
  } else if (type == WStype_TEXT) {
    if (length == 4 && memcmp(payload, "ping", 4) == 0) {
      companionWs.sendTXT(client, "{\"schema_version\":1,\"type\":\"pong\"}");
    } else {
      companionHandleDownlink(payload, length);
    }
  }
  // 麥克風的 binary frame 只往 AIPC 方向送（ESP32 -> AIPC），不會有 client 送
  // binary frame 過來，所以這裡不用處理 WStype_BIN。
}

void setup() {
  Serial.begin(MONITOR_SPEED);
  delay(1200);
  Serial.println("\nStage 13: companion app (LCD + FSR + IMU + buzzer + mic, HTTP + WebSocket)");
  snprintf(companionDeviceId, sizeof(companionDeviceId), "esp32-%012llx", ESP.getEfuseMac());
  snprintf(companionBootId, sizeof(companionBootId), "%08lx", (unsigned long)esp_random());

  if (TELEMETRY_FSR_ENABLED) {
    analogReadResolution(ADC_RESOLUTION_BITS);
    analogSetPinAttenuation(PIN_FSR1_SENSE, ADC_ATTEN);
    analogSetPinAttenuation(PIN_FSR2_SENSE, ADC_ATTEN);
  }
  if (TELEMETRY_IMU_ENABLED) {
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, I2C_FREQ_HZ);
    Wire.setTimeOut(20);
    companionImuReady = companionMpu.begin(IMU_I2C_ADDR, &Wire);
    if (companionImuReady) {
      companionMpu.setAccelerometerRange(MPU6050_RANGE_8_G);
      companionMpu.setGyroRange(MPU6050_RANGE_500_DEG);
      companionMpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
    } else {
      companionImuRawFallback = companionImuRawWake();
      Serial.printf("IMU raw fallback: %d\n", companionImuRawFallback);
    }
  }
  Serial.printf("FSR enabled: %d; IMU initialized: %d\n", TELEMETRY_FSR_ENABLED, companionImuReady);

  pinMode(PIN_BUZZER, OUTPUT);
  if (!micInit()) {
    Serial.println("mic init failed；麥克風串流會停擺，其他功能不受影響");
  }
  lcdInit();

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
    companionMdnsStart();  // AP 模式 IP 立刻就知道（192.168.4.1），可以馬上啟動
  }

  companionSampleSensors();
  companionHttp.on("/", HTTP_GET, []() {
    String page = FPSTR(TELEMETRY_DASHBOARD);
    page.replace("__WS_PORT__", String(WS_PORT));
    companionHttp.send(200, "text/html; charset=utf-8", page);
  });
  companionHttp.on("/api/v1/health", HTTP_GET, []() {
    String body = "{\"schema_version\":1,\"ok\":true,\"device_id\":\"" + String(companionDeviceId)
      + "\",\"wifi_mode\":\"" + (TELEMETRY_USE_STA ? "sta" : "ap")
      + "\",\"imu_ok\":" + (companionImuSampleOk ? "true" : "false") + "}";
    companionHttp.sendHeader("Cache-Control", "no-store");
    companionHttp.send(200, "application/json", body);
  });
  companionHttp.on("/api/v1/telemetry", HTTP_GET, []() {
    companionHttp.sendHeader("Cache-Control", "no-store");
    companionHttp.send(200, "application/json", companionLatestSample);
  });
  companionHttp.onNotFound([]() {
    companionHttp.send(404, "application/json", "{\"type\":\"error\",\"code\":\"not_found\"}");
  });
  companionHttp.begin();
  companionWs.begin();
  companionWs.onEvent(companionWsEvent);
  companionWs.enableHeartbeat(15000, 3000, 2);
}

void loop() {
  companionHttp.handleClient();
  companionWs.loop();

  const uint32_t now = millis();
  static uint32_t lastSample = 0;
  if (now - lastSample >= TELEMETRY_PERIOD_MS) {
    lastSample = now;
    companionSampleSensors();
    companionWs.broadcastTXT(companionLatestSample);
  }

  // 麥克風非阻塞讀取：DMA buffer 還沒滿就回 0，不會卡住上面的 WS/HTTP 處理。
  const size_t micBytes = micReadChunk();
  if (micBytes > 0) {
    companionWs.broadcastBIN((uint8_t *)s_micPcm, micBytes);
  }

  lcdUpdate(now);

  if (TELEMETRY_USE_STA) {
    static bool wasConnected = false;
    static uint32_t lastRetry = 0;
    const bool connected = WiFi.status() == WL_CONNECTED;
    if (connected && !wasConnected) {
      Serial.printf("Dashboard: http://%s/\n", WiFi.localIP().toString().c_str());
      companionMdnsStart();
    }
    if (!connected && wasConnected) Serial.println("WiFi disconnected; retrying...");
    if (!connected && now - lastRetry >= 10000) {
      lastRetry = now;
      WiFi.reconnect();
    }
    wasConnected = connected;
  }
}
