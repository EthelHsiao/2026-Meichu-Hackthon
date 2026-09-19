// ============================================================
//  ESP32 陪伴裝置 — 硬體 bring-up
//  以 APP_STAGE 巨集切換階段，由 platformio.ini 的 env 決定。
// ============================================================
#include <Arduino.h>
#include "board_config.h"

#ifndef APP_STAGE
#error "APP_STAGE 沒有定義。請從 PlatformIO 的 env 建置（例如 s1_serial），不要直接按 VS Code 的 Run。"
#endif

// ============================================================
//  Step 1 — 最小 Serial 測試
//  目的：只證明「電腦 ↔ ESP32 的 USB Serial 通道會動」。
//  不碰 FSR / IMU / LCD，不用任何外部 library，也不依賴板上 LED 腳位
//  （不同 38-pin 板的 LED 可能在 GPIO2、GPIO5 或根本沒有）。
// ============================================================
#if APP_STAGE == 1

static uint32_t g_seq = 0;
static uint32_t g_lastBeatMs = 0;

// 把重置原因印出來：之後接 LCD 發生 brownout 重啟時，這行是關鍵線索
static const char *resetReasonText() {
  switch (esp_reset_reason()) {
    case ESP_RST_POWERON:  return "POWERON (插電/拔插USB)";
    case ESP_RST_EXT:      return "EXT (外部reset腳)";
    case ESP_RST_SW:       return "SW (軟體重啟)";
    case ESP_RST_PANIC:    return "PANIC (程式當掉)";
    case ESP_RST_INT_WDT:  return "INT_WDT";
    case ESP_RST_TASK_WDT: return "TASK_WDT";
    case ESP_RST_WDT:      return "WDT";
    case ESP_RST_BROWNOUT: return "BROWNOUT (供電不足) <-- 接模組後看到這個就是電源問題";
    case ESP_RST_SDIO:     return "SDIO";
    default:               return "UNKNOWN";
  }
}

// 這段是 Step 0「確認板型」的實際手段：
// 不是猜的，是晶片自己回報的。輸出請貼回給 agent 更新 board_config.h。
static void printIdentityBanner() {
  Serial.println();
  Serial.println(F("============================================================"));
  Serial.println(F(" ESP32 bring-up / Stage 1 : minimal serial"));
  Serial.println(F("============================================================"));
  Serial.printf (" 賣場料號(使用者提供) : %s\n", BOARD_SKU_NOTE);
  Serial.printf (" platformio board 候選 : %s\n", BOARD_CANDIDATE);
  Serial.println(F("------------------------------------------------------------"));
  Serial.println(F(" 以下由晶片自己回報，這才是板型的實際證據："));
  Serial.printf ("   chip model     : %s\n", ESP.getChipModel());
  Serial.printf ("   chip revision  : %d\n", ESP.getChipRevision());
  Serial.printf ("   cores          : %d\n", ESP.getChipCores());
  Serial.printf ("   cpu freq       : %u MHz\n", (unsigned)ESP.getCpuFreqMHz());
  Serial.printf ("   flash size     : %u bytes\n", (unsigned)ESP.getFlashChipSize());
  Serial.printf ("   free heap      : %u bytes\n", (unsigned)ESP.getFreeHeap());
  Serial.printf ("   efuse MAC      : %012llX\n", ESP.getEfuseMac());
  Serial.printf ("   arduino-esp32  : %s\n", ESP.getSdkVersion());
  Serial.printf ("   reset reason   : %s\n", resetReasonText());
  Serial.println(F("------------------------------------------------------------"));
  Serial.printf (" baud = %d（必須與 monitor_speed 一致，亂碼通常是這裡不合）\n", MONITOR_SPEED);
  Serial.println(F(" 你可以在 Serial Monitor 打字後按 Enter，板子會 echo 回來，"));
  Serial.println(F(" 證明 host -> board 方向也通（同時也確認你選對 COM port）。"));
  Serial.println(F("============================================================"));
  Serial.println();
}

void setup() {
  Serial.begin(MONITOR_SPEED);
  // 有些板是 native USB CDC，剛開機時 host 還沒列舉完就印字會掉頭幾行。
  // 這裡不用 while(!Serial) 卡死（非 CDC 板會永遠等不到），改成固定短延遲。
  delay(1200);
  printIdentityBanner();
  g_lastBeatMs = millis();
}

void loop() {
  const uint32_t now = millis();

  // ---- 週期性 heartbeat：驗收就是看這串數字有沒有一直變 ----
  if (now - g_lastBeatMs >= HEARTBEAT_PERIOD_MS) {
    g_lastBeatMs += HEARTBEAT_PERIOD_MS;
    g_seq++;
    Serial.printf("HB seq=%lu t_ms=%lu uptime_s=%.1f heap=%u\n",
                  (unsigned long)g_seq,
                  (unsigned long)now,
                  now / 1000.0f,
                  (unsigned)ESP.getFreeHeap());
  }

  // ---- 反向通道：把收到的字回傳，確認不是在讀別的序列裝置 ----
  while (Serial.available() > 0) {
    const int c = Serial.read();
    if (c == '\n' || c == '\r') {
      Serial.println();
    } else {
      Serial.printf("[echo] 0x%02X '%c'\n", c, (c >= 32 && c < 127) ? (char)c : '.');
    }
  }
}

// ============================================================
//  Step 2 — 單一 FSR1 分壓 raw ADC
//  目的：只證明 FSR1（GPIO34）這一路分壓電路能讀到「按下去變大、
//  放開變小」的即時數值。先只做一路，兩路都通了才進 Step 3。
//  接線：CONFIRMED_HARDWARE_AND_WIRING.md 第二、三節 ——
//    3.3V -> FSR1 -> SENSE 節點(同時接 FSR_FIXED_R_OHM 與 D34) -> GND
// ============================================================
#elif APP_STAGE == 2

void setup() {
  Serial.begin(MONITOR_SPEED);
  delay(1200);

  analogReadResolution(ADC_RESOLUTION_BITS);
  analogSetPinAttenuation(PIN_FSR1_SENSE, ADC_ATTEN);

  Serial.println();
  Serial.println(F("============================================================"));
  Serial.println(F(" ESP32 bring-up / Stage 2 : FSR1 raw ADC"));
  Serial.println(F("============================================================"));
  Serial.printf (" PIN_FSR1_SENSE  : GPIO%d (ADC1)\n", PIN_FSR1_SENSE);
  Serial.printf (" 固定電阻        : %d ohm\n", FSR_FIXED_R_OHM);
  Serial.printf (" ADC             : %d-bit\n", ADC_RESOLUTION_BITS);
  Serial.println(F("------------------------------------------------------------"));
  Serial.println(F(" 沒碰時應該是穩定低基線；按下去數字上升、放開會回去。"));
  Serial.println(F(" 不要求特定數值，要求的是「可重複的變化」。"));
  Serial.println(F(" 記下三個數字：基線 / 一般按壓 / 飽和值，Step 3 選電阻會用到。"));
  Serial.println(F("============================================================"));
  Serial.println();
}

void loop() {
  static uint32_t lastSample = 0;
  const uint32_t now = millis();
  if (now - lastSample < FSR_SAMPLE_PERIOD_MS) return;
  lastSample = now;

  const int raw = analogRead(PIN_FSR1_SENSE);
  // ADC 讀值有已知非線性，這裡只是粗略估算給人看，不是精密量測，不要拿來做力學校準。
  const float volts = raw * (3.3f / ((1 << ADC_RESOLUTION_BITS) - 1));
  Serial.printf("FSR1 raw=%4d  ~%.2fV\n", raw, volts);
}

// ============================================================
//  Step 3 — 雙 FSR，Serial Plotter 曲線
//  目的：FSR1（GPIO34）/ FSR2（GPIO35）各自獨立、互不干擾。
//  兩片必須用各自獨立的 SENSE 節點與各自獨立的 FSR_FIXED_R_OHM 電阻，
//  絕對不能共用同一條 SENSE 排，不然兩條曲線會完全同步。
//  輸出用 label:value 格式：Serial Monitor 看是正常文字，開 Serial
//  Plotter 會自動畫出四條有圖例的曲線，不用為了畫圖和除錯各寫一套。
// ============================================================
#elif APP_STAGE == 3

static const int SMOOTH_WINDOW = 4;  // 簡單移動平均，只是讓數字不要跳太花，不是正式濾波
static int s_fsr1Buf[SMOOTH_WINDOW] = {0};
static int s_fsr2Buf[SMOOTH_WINDOW] = {0};
static int s_bufIndex = 0;

static int smooth(int *buf, int newVal) {
  buf[s_bufIndex % SMOOTH_WINDOW] = newVal;
  long sum = 0;
  for (int i = 0; i < SMOOTH_WINDOW; i++) sum += buf[i];
  return sum / SMOOTH_WINDOW;
}

void setup() {
  Serial.begin(MONITOR_SPEED);
  delay(1200);

  analogReadResolution(ADC_RESOLUTION_BITS);
  analogSetPinAttenuation(PIN_FSR1_SENSE, ADC_ATTEN);
  analogSetPinAttenuation(PIN_FSR2_SENSE, ADC_ATTEN);

  // 這一段只印一次，是給人看的說明，不會混進下面連續的 Plotter 資料流
  Serial.println();
  Serial.println(F("=== Stage 3: FSR1 + FSR2 Serial Plotter ==="));
  Serial.printf (" FSR1 = GPIO%d / FSR2 = GPIO%d\n", PIN_FSR1_SENSE, PIN_FSR2_SENSE);
  Serial.println(F(" 只按 FSR1 應該只有 FSR1 的曲線動，FSR2 不動；反之亦然。"));
  Serial.println(F(" 兩條完全同步通常代表兩個 SENSE 節點誤接在一起。"));
  Serial.println();
}

void loop() {
  static uint32_t lastSample = 0;
  const uint32_t now = millis();
  if (now - lastSample < FSR_SAMPLE_PERIOD_MS) return;
  lastSample = now;

  const int raw1 = analogRead(PIN_FSR1_SENSE);
  const int raw2 = analogRead(PIN_FSR2_SENSE);
  const int s1 = smooth(s_fsr1Buf, raw1);
  const int s2 = smooth(s_fsr2Buf, raw2);
  s_bufIndex++;

  Serial.print(F("FSR1_raw:"));    Serial.print(raw1);
  Serial.print('\t');
  Serial.print(F("FSR1_smooth:")); Serial.print(s1);
  Serial.print('\t');
  Serial.print(F("FSR2_raw:"));    Serial.print(raw2);
  Serial.print('\t');
  Serial.print(F("FSR2_smooth:")); Serial.println(s2);
}

// ============================================================
//  Step 4 — MPU6050：I2C scanner + 六軸讀值，顯示在 LCD
//  接線：GY-521 模組，VCC->VIN(5V，板上有 3.3V 穩壓器且上拉電阻接
//  在穩壓後的 3.3V，SDA/SCL 對 ESP32 安全) GND->GND SCL->D22 SDA->D21，
//  XDA/XCL/AD0/INT 不接（AD0 浮接=位址 0x68）。
//  流程照接線工作台第 08 章：先跑 I2C scanner 確認 0x68 有回應，
//  再初始化 MPU6050 驅動；掃不到就不要往下猜，直接停在錯誤狀態。
// ============================================================
#elif APP_STAGE == 4
#include <SPI.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>

Adafruit_ST7735 tft(PIN_LCD_CS, PIN_LCD_DC, PIN_LCD_RST);
Adafruit_MPU6050 mpu;

static bool s_mpuOk = false;

// 只在開機時跑一次，把結果同時印到 Serial 跟 LCD。
// 回傳有沒有掃到 targetAddr，不代表那個位址上一定是 MPU6050
// （只代表「有東西在那個位址回應」），型號仍以 mpu.begin() 的結果為準。
static bool i2cScanFor(uint8_t targetAddr) {
  bool found = false;
  Serial.println(F("I2C scanner 開始..."));
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    const uint8_t err = Wire.endTransmission();
    if (err == 0) {
      Serial.printf("  找到裝置，位址 0x%02X%s\n", addr, addr == targetAddr ? "  <-- 目標" : "");
      if (addr == targetAddr) found = true;
    }
  }
  if (!found) Serial.printf("沒掃到 0x%02X\n", targetAddr);
  return found;
}

void setup() {
  Serial.begin(MONITOR_SPEED);
  delay(1200);

  Serial.println();
  Serial.println(F("============================================================"));
  Serial.println(F(" ESP32 bring-up / Stage 4 : MPU6050 I2C scanner + LCD 讀值"));
  Serial.println(F("============================================================"));

  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, I2C_FREQ_HZ);

  tft.initR(INITR_BLACKTAB);
  tft.setRotation(0);
  tft.fillScreen(ST77XX_BLACK);
  tft.setTextSize(1);
  tft.setTextColor(ST77XX_WHITE);
  tft.setCursor(4, 4);
  tft.println(F("MPU6050 test"));

  const bool scanned = i2cScanFor(IMU_I2C_ADDR);
  tft.setCursor(4, 16);
  if (scanned) {
    tft.setTextColor(ST77XX_GREEN);
    tft.println(F("I2C scan: found 0x68"));
  } else {
    tft.setTextColor(ST77XX_RED);
    tft.println(F("I2C scan: 0x68 NOT FOUND"));
    Serial.println(F("先查：SDA/SCL 是否接反(21<->22)、GND 有沒有共地、VCC 是否真的有電。"));
  }

  if (scanned) {
    s_mpuOk = mpu.begin(IMU_I2C_ADDR, &Wire);
    if (s_mpuOk) {
      mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
      mpu.setGyroRange(MPU6050_RANGE_500_DEG);
      mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
      Serial.println(F("MPU6050 初始化成功"));
    } else {
      Serial.println(F("mpu.begin() 失敗：掃得到位址，但驅動初始化不成功"));
    }
  }

  tft.setCursor(4, 28);
  tft.setTextColor(s_mpuOk ? ST77XX_GREEN : ST77XX_RED);
  tft.println(s_mpuOk ? F("mpu.begin(): OK") : F("mpu.begin(): FAIL"));

  delay(600);  // 讓上面幾行狀態訊息留在螢幕上一下，之後才開始洗掉重畫數值區
}

static void drawImuValues(const sensors_event_t &a, const sensors_event_t &g) {
  // 只清數值那塊矩形，上面的狀態列留著不動
  tft.fillRect(0, 44, LCD_WIDTH, LCD_HEIGHT - 44, ST77XX_BLACK);
  tft.setTextSize(1);
  tft.setTextColor(ST77XX_WHITE);

  tft.setCursor(4, 46);
  tft.println(F("accel (m/s^2)"));
  tft.setCursor(4, 58);  tft.printf("ax %+6.2f\n", a.acceleration.x);
  tft.setCursor(4, 68);  tft.printf("ay %+6.2f\n", a.acceleration.y);
  tft.setCursor(4, 78);  tft.printf("az %+6.2f\n", a.acceleration.z);

  tft.setCursor(4, 94);
  tft.println(F("gyro (rad/s)"));
  tft.setCursor(4, 106); tft.printf("gx %+6.2f\n", g.gyro.x);
  tft.setCursor(4, 116); tft.printf("gy %+6.2f\n", g.gyro.y);
  tft.setCursor(4, 126); tft.printf("gz %+6.2f\n", g.gyro.z);
}

void loop() {
  if (!s_mpuOk) {
    // 初始化失敗就不要無限重試，狀態已經印在螢幕跟 Serial 上了
    delay(1000);
    return;
  }

  static uint32_t lastSample = 0;
  const uint32_t now = millis();
  if (now - lastSample < 20) return;  // ~50Hz，跟 FSR 取樣節奏一致
  lastSample = now;

  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);

  Serial.printf("ax=%+.2f ay=%+.2f az=%+.2f  gx=%+.2f gy=%+.2f gz=%+.2f  (m/s^2, rad/s)\n",
                a.acceleration.x, a.acceleration.y, a.acceleration.z,
                g.gyro.x, g.gyro.y, g.gyro.z);

  static uint32_t lastDraw = 0;
  if (now - lastDraw >= LCD_UPDATE_PERIOD_MS) {
    lastDraw = now;
    drawImuValues(a, g);
  }
}

// ============================================================
//  Step 5 — LCD 測試畫面：顔文字表情（含眨眼）+ FSR1 即時壓力
//  接線：8 腳小紅板（A 型），使用者已目視確認（2026-09-18）：
//    VCC->3V3  GND->GND  SCL->D18  SDA->D23  RES->D25  DC->D26  CS->D27  BLK->3V3
//  顔文字用內建點陣字型直接印文字組成，不用另外畫向量圖形；
//  「眨眼」只是把眼睛字元從 ^ 換成 -，短暫顯示後換回來。
//  畫面更新跟 FSR 取樣分開排程（LCD_UPDATE_PERIOD_MS），
//  避免 SPI 畫面更新拖慢感測取樣，也避免整片 fillScreen 造成閃爍
//  ——每次只清「表情那一塊」或「讀值那一塊」矩形，不重畫整個螢幕。
// ============================================================
#elif APP_STAGE == 5
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>

Adafruit_ST7735 tft(PIN_LCD_CS, PIN_LCD_DC, PIN_LCD_RST);

// ---- 顔文字表情 ----
static const char *FACE_OPEN  = "(^_^)";
static const char *FACE_BLINK = "(-_-)";

static const int FACE_TEXT_SIZE = 4;                    // 每字元約 6*size px 寬
static const int FACE_CHAR_W    = 6 * FACE_TEXT_SIZE;
static const int FACE_CHAR_H    = 8 * FACE_TEXT_SIZE;
static const int FACE_Y         = 30;                    // 表情區塊上緣

static bool     s_blinking    = false;
static uint32_t s_nextBlinkAt = 0;
static uint32_t s_blinkUntil  = 0;

static void drawFace(const char *face) {
  const int textW = (int)strlen(face) * FACE_CHAR_W;
  const int x = (LCD_WIDTH - textW) / 2;
  // 只清表情那一塊矩形，不要 fillScreen 整片重畫，不然會一直閃
  tft.fillRect(0, FACE_Y, LCD_WIDTH, FACE_CHAR_H, ST77XX_BLACK);
  tft.setTextSize(FACE_TEXT_SIZE);
  tft.setTextColor(ST77XX_WHITE);
  tft.setCursor(x, FACE_Y);
  tft.print(face);
}

static void updateBlink(uint32_t now) {
  if (!s_blinking) {
    if (now >= s_nextBlinkAt) {
      s_blinking   = true;
      s_blinkUntil = now + 160;                 // 眨眼持續 160ms
      drawFace(FACE_BLINK);
    }
  } else if (now >= s_blinkUntil) {
    s_blinking = false;
    // 下次眨眼間隔 2.5–5 秒，帶一點隨機不然會看起來像機械式閃爍
    s_nextBlinkAt = now + 2500 + (esp_random() % 2500);
    drawFace(FACE_OPEN);
  }
}

// ---- 底部：FSR1 即時壓力（只顯示 FSR1，對齊使用者這次的要求）----
static const int BAR_Y     = 130;
static const int BAR_H     = 14;
static const int BAR_X     = 10;
static const int BAR_MAX_W = LCD_WIDTH - 2 * BAR_X;

static void drawFsrReadout(int raw) {
  const int adcMax = (1 << ADC_RESOLUTION_BITS) - 1;
  const int barW = (int)((long)raw * BAR_MAX_W / adcMax);

  // 只清「文字 + 長條」這一塊，跟表情區塊分開，互不干擾
  tft.fillRect(0, BAR_Y - 18, LCD_WIDTH, 18 + BAR_H + 4, ST77XX_BLACK);

  tft.setTextSize(1);
  tft.setTextColor(ST77XX_WHITE);
  tft.setCursor(BAR_X, BAR_Y - 14);
  tft.printf("FSR1 raw: %4d", raw);

  tft.drawRect(BAR_X, BAR_Y, BAR_MAX_W, BAR_H, ST77XX_WHITE);
  if (barW > 0) {
    tft.fillRect(BAR_X, BAR_Y, barW, BAR_H, ST77XX_GREEN);
  }
}

void setup() {
  Serial.begin(MONITOR_SPEED);
  delay(1200);

  analogReadResolution(ADC_RESOLUTION_BITS);
  analogSetPinAttenuation(PIN_FSR1_SENSE, ADC_ATTEN);

  Serial.println();
  Serial.println(F("============================================================"));
  Serial.println(F(" ESP32 bring-up / Stage 5 : LCD 顔文字 + FSR1 讀值"));
  Serial.println(F("============================================================"));
  Serial.println(F(" 驗收順序（不要跳）："));
  Serial.println(F(" 1. 背光亮 —— 只證明有電，不證明 SPI 通了"));
  Serial.println(F(" 2. 螢幕變黑底（fillScreen 成功）—— 證明 SPI 初始化成功"));
  Serial.println(F(" 3. 中間出現 (^_^)，會不定期眨眼變成 (-_-) 再變回來"));
  Serial.println(F(" 4. 最下面出現 FSR1 raw 數字跟長條，按 FSR1 長條會變長"));
  Serial.println(F(" 顏色不對或邊緣有雜線：改 board_config.h 的 initR() 參數"));
  Serial.println(F(" 改成 INITR_GREENTAB 或 INITR_REDTAB 再重燒一次。"));
  Serial.println(F("============================================================"));
  Serial.println();

  tft.initR(INITR_BLACKTAB);
  tft.setRotation(0);
  tft.fillScreen(ST77XX_BLACK);

  s_nextBlinkAt = millis() + 2000;
  drawFace(FACE_OPEN);
}

void loop() {
  const uint32_t now = millis();
  updateBlink(now);

  // FSR 取樣維持原本的節奏，不受 LCD 拖累
  static uint32_t lastSample = 0;
  static int      lastRaw    = 0;
  if (now - lastSample >= FSR_SAMPLE_PERIOD_MS) {
    lastSample = now;
    lastRaw = analogRead(PIN_FSR1_SENSE);
  }

  // LCD 更新用自己的、慢一點的節奏，畫面不拖慢取樣，也不會閃到眼花
  static uint32_t lastDraw = 0;
  if (now - lastDraw >= LCD_UPDATE_PERIOD_MS) {
    lastDraw = now;
    drawFsrReadout(lastRaw);
  }
}

// ============================================================
//  Step 7 — WiFi SoftAP + HTTP hello world
//  目的：只證明「ESP32 的 WiFi 硬體會動、電腦連得上」。
//  用 Arduino-ESP32 內建的 WebServer.h，不需要額外 library。
//  這是加 WebSocket（Step 8）之前的地基測試，不是最終要用的通道。
// ============================================================
#elif APP_STAGE == 7
#include <WiFi.h>
#include <WebServer.h>

WebServer server(80);

static void handleRoot() {
  server.send(200, "text/plain", "Hello from ESP32");
}

void setup() {
  Serial.begin(MONITOR_SPEED);
  delay(1200);
  Serial.println(F("============================================================"));
  Serial.println(F(" ESP32 bring-up / Stage 7 : WiFi SoftAP + HTTP"));
  Serial.println(F("============================================================"));

  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD);
  Serial.print(F(" AP SSID        : "));
  Serial.println(WIFI_AP_SSID);
  Serial.print(F(" AP password    : "));
  Serial.println(WIFI_AP_PASSWORD);
  Serial.print(F(" AP IP address  : "));
  Serial.println(WiFi.softAPIP());  // 應該是 192.168.4.1
  Serial.println(F("------------------------------------------------------------"));
  Serial.println(F(" 驗收步驟："));
  Serial.println(F(" 1. 電腦連上面那個 WiFi SSID"));
  Serial.println(F(" 2. 開終端機打： curl http://192.168.4.1/"));
  Serial.println(F(" 3. 看到 \"Hello from ESP32\" 就算 Stage 7 過關"));
  Serial.println(F("============================================================"));

  server.on("/", handleRoot);
  server.begin();
  Serial.println(F("HTTP server started"));
}

void loop() {
  server.handleClient();
}

// ============================================================
//  Step 8 — WiFi SoftAP + WebSocket
//  目的：真正要用的通道。FSR 讀值要持續上傳、LCD 顯示內容要持續
//  下發，都是連續雙向的小封包，握手一次後維持長連線，比 Step 7
//  的 HTTP 更適合。收到訊息先印到 Serial 驗證雙向都通，
//  之後再接上真正的 FSR / LCD 邏輯。
// ============================================================
#elif APP_STAGE == 8
#include <WiFi.h>
#include <WebSocketsServer.h>

WebSocketsServer webSocket(WS_PORT);

static void webSocketEvent(uint8_t num, WStype_t type, uint8_t *payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      Serial.printf("[%u] 連線成功\n", num);
      break;
    case WStype_DISCONNECTED:
      Serial.printf("[%u] 斷線\n", num);
      break;
    case WStype_TEXT:
      Serial.printf("收到: %s\n", payload);
      break;
    default:
      break;
  }
}

void setup() {
  Serial.begin(MONITOR_SPEED);
  delay(1200);
  Serial.println(F("============================================================"));
  Serial.println(F(" ESP32 bring-up / Stage 8 : WiFi SoftAP + WebSocket"));
  Serial.println(F("============================================================"));

  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD);
  Serial.print(F(" AP IP address  : "));
  Serial.println(WiFi.softAPIP());
  Serial.printf (" WebSocket URL  : ws://%s:%d/\n", WiFi.softAPIP().toString().c_str(), WS_PORT);
  Serial.println(F("------------------------------------------------------------"));
  Serial.println(F(" 電腦端用 Python 連上去測試（pip install websockets）："));
  Serial.println(F("   import asyncio, websockets"));
  Serial.println(F("   async def main():"));
  Serial.println(F("       async with websockets.connect(\"ws://192.168.4.1:81/\") as ws:"));
  Serial.println(F("           while True: print(await ws.recv())"));
  Serial.println(F("   asyncio.run(main())"));
  Serial.println(F("============================================================"));

  webSocket.begin();
  webSocket.onEvent(webSocketEvent);
}

void loop() {
  webSocket.loop();  // 一定要放在 loop() 裡，負責處理 WebSocket 事件

  static uint32_t lastSend = 0;
  const uint32_t now = millis();
  if (now - lastSend >= 1000) {
    lastSend = now;
    // Stage 8 先送假的心跳資料驗證通道兩端都通。
    // 等 Stage 3（雙 FSR）真的量到讀值之後，把這行換成：
    //   analogRead(PIN_FSR1_SENSE) / analogRead(PIN_FSR2_SENSE)
    String json = "{\"hb\":" + String(now) + "}";
    webSocket.broadcastTXT(json);
  }
}

// ============================================================
//  Step 6 —— 尚未實作
//  Step 2/3（FSR）、Step 4（MPU6050 + LCD）、Step 5（LCD 顔文字 +
//  FSR1）都已完成，見上方。Step 6 是 FSR + IMU + LCD 三個模組的整合，
//  等這幾階各自先在螢幕上單獨驗證過，才合併成一份 telemetry。
// ============================================================
#else

void setup() {
  Serial.begin(MONITOR_SPEED);
  delay(1200);
  Serial.printf("\nAPP_STAGE=%d 尚未實作。\n", APP_STAGE);
  Serial.println("目前已實作：s1_serial、s2_fsr1、s3_fsr2、s4_imu、s5_lcd、s7_wifi_http、s8_wifi_ws。");
}

void loop() {
  delay(1000);
}

#endif
