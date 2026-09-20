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
static bool s_rawFallback = false;  // WHO_AM_I 讀得到但不是 0x68/0x70，繞過 Adafruit 驅動直接讀暫存器驗證

// 大多數 Invensense 系列（MPU6050/6500/9250/9255...）不管型號，
// 0x3B 開始的 14 個 byte 都是同一種排列：
//   ACCEL_XOUT_H/L, ACCEL_YOUT_H/L, ACCEL_ZOUT_H/L,
//   TEMP_OUT_H/L, GYRO_XOUT_H/L, GYRO_YOUT_H/L, GYRO_ZOUT_H/L
// 就算 WHO_AM_I 對不上任何已知型號、驅動不敢初始化，這組原始暫存器
// 通常還是讀得到東西——用來憑經驗確認「這真的是一顆會動的六軸感測器」，
// 不依賴型號比對。
static bool readRawImu(uint8_t i2cAddr, int16_t out[7]) {
  Wire.beginTransmission(i2cAddr);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;
  const uint8_t n = Wire.requestFrom(i2cAddr, (uint8_t)14);
  if (n != 14) return false;
  for (uint8_t i = 0; i < 7; i++) {
    const uint8_t hi = Wire.read();
    const uint8_t lo = Wire.read();
    out[i] = (int16_t)((hi << 8) | lo);
  }
  return true;
}


// 只在開機時跑一次，把結果同時印到 Serial 跟 LCD。
// 回傳有沒有掃到 targetAddr，不代表那個位址上一定是 MPU6050
// （只代表「有東西在那個位址回應」），型號仍以 mpu.begin() 的結果為準。
// 直接讀 WHO_AM_I 暫存器（位址 0x75），不透過 Adafruit 驅動。
// 目的：分辨「i2c scan 有回應」跟「mpu.begin() 失敗」中間到底發生什麼事——
// 真正的 MPU6050 這個暫存器應該回 0x68；如果讀到 0x70，代表這顆其實是
// MPU6500（很多賣場把 GY-521 外殼底下換成 MPU6500，腳位/外觀一樣但晶片不同，
// Adafruit_MPU6050::begin() 內部會比對這個值，不是 0x68 就直接回傳 false）。
// 0xFF 代表讀不到資料（i2c 通訊本身有問題，跟 scan 找得到位址不衝突，
// scan 只送一個位元組確認有沒有人應答，begin() 要做更多次真正的讀寫）。
static uint8_t readWhoAmI(uint8_t i2cAddr) {
  Wire.beginTransmission(i2cAddr);
  Wire.write(0x75);  // WHO_AM_I register, MPU6050/6500/9250 通用
  if (Wire.endTransmission(false) != 0) return 0xFF;
  Wire.requestFrom(i2cAddr, (uint8_t)1);
  if (Wire.available()) return Wire.read();
  return 0xFF;
}

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
    const uint8_t whoAmI = readWhoAmI(IMU_I2C_ADDR);
    Serial.printf("WHO_AM_I (reg 0x75) = 0x%02X  (真正 MPU6050 應該是 0x68；"
                  "0x70 代表這顆其實是 MPU6500 相容品；0xFF 代表這步驟本身讀不到資料)\n", whoAmI);
    tft.setCursor(4, 108);
    tft.setTextColor(ST77XX_YELLOW);
    tft.printf("WHO_AM_I: 0x%02X\n", whoAmI);

    s_mpuOk = mpu.begin(IMU_I2C_ADDR, &Wire);
    if (s_mpuOk) {
      mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
      mpu.setGyroRange(MPU6050_RANGE_500_DEG);
      mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
      Serial.println(F("MPU6050 初始化成功"));
    } else {
      Serial.println(F("mpu.begin() 失敗：WHO_AM_I 不是 Adafruit 驅動認得的型號，"
                        "改用原始暫存器讀取來驗證晶片是不是還活著"));
      if (whoAmI != 0xFF) {
        s_rawFallback = true;
        tft.setCursor(4, 118);
        tft.setTextColor(ST77XX_CYAN);
        tft.println(F("raw fallback mode"));
      }
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
    if (s_rawFallback) {
      static uint32_t lastRaw = 0;
      const uint32_t now = millis();
      if (now - lastRaw >= 200) {
        lastRaw = now;
        int16_t raw[7];
        if (readRawImu(IMU_I2C_ADDR, raw)) {
          Serial.printf("RAW ax=%d ay=%d az=%d  gx=%d gy=%d gz=%d\n",
                        raw[0], raw[1], raw[2], raw[4], raw[5], raw[6]);
          // 螢幕空間有限，一行放兩軸；6 軸都顯示（Serial 一直都有全部 6 軸，
          // 之前只是畫面上先省略 gx/gy，不是資料本身就沒有）。
          tft.fillRect(0, 128, LCD_WIDTH, LCD_HEIGHT - 128, ST77XX_BLACK);
          tft.setCursor(4, 130);
          tft.setTextColor(ST77XX_WHITE);
          tft.printf("ax%+6d ay%+6d\naz%+6d gx%+6d\ngy%+6d gz%+6d\n",
                      raw[0], raw[1], raw[2], raw[4], raw[5], raw[6]);
        } else {
          Serial.println(F("raw fallback 讀取失敗（14 byte 沒讀齊）"));
        }
      }
      return;
    }
    // 初始化失敗，且沒有 fallback 可用：狀態已經印在螢幕跟 Serial 上了
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
//  Step 5 — LCD 黑貓臉單獨驗證（只有螢幕，沒有感測器／麥克風／蜂鳴器）
//  臉與台詞的實作在 include/lcd_faces.h，跟正式用的 Stage 13（s13_companion）
//  共用同一份，兩邊畫出來完全一樣。這個 env 的用途是「只驗螢幕」：
//  接線有沒有對、顏色/方向對不對、中文有沒有正常顯示、表情好不好看。
//
//  接線：8 腳小紅板（A 型），使用者已目視確認（2026-09-18）：
//    VCC->3V3  GND->GND  SCL->D18  SDA->D23  RES->D25  DC->D26  CS->D27  BLK->3V3
//
//  通訊：WiFi SoftAP + WebSocket（ws://192.168.4.1:81/），格式見
//  docs/api.html §①。Serial Monitor 也吃同樣的 JSON，沒連 WiFi 也能測：
//    {"t":"expr","expr":"thinking"}                  → 換情緒
//    {"t":"say","expr":"sad","text":"你要走了嗎"}     → 排一句台詞
//    {"t":"say","text":"嗯…讓我","done":false}        → 串流：同一句陸續補字…
//    {"t":"say","text":"想想"}                        →   …done 省略 = true，這句結束
//    {"t":"clear"}                                   → 清掉台詞和佇列
//  Serial 捷徑：/idle /thinking …換情緒、/demo 輪播、其他文字直接當一句台詞。
// ============================================================
#elif APP_STAGE == 5
#include <WiFi.h>
#include <WebSocketsServer.h>
#include <ArduinoJson.h>
#include "lcd_faces.h"

WebSocketsServer webSocket(WS_PORT);

struct DemoStep { const char *expr; const char *text; };   // text = nullptr：只換表情、安靜一陣子
static const DemoStep DEMO[] = {
  {"neutral",   "嗨，我在這裡陪你。"},
  {"idle",      nullptr},
  {"thinking",  "嗯…讓我想想這個 bug 是從哪裡來的"},
  {"worried",   "這個錯誤已經卡 40 分鐘了，要不要換個方法？"},
  {"surprised", "哇！居然一次就編譯成功了！"},
  {"love",      "你今天好認真，我好喜歡看你寫程式"},
  {"sad",       "你要走了嗎…再陪我一下下好不好"},
  {"sleepy",    "好睏…已經凌晨兩點了，明天再寫吧"},
  {"dizzy",     "被你搖得頭好暈…世界在轉圈圈"},
};
static const int DEMO_LEN = sizeof(DEMO) / sizeof(DEMO[0]);

static bool     s_demo = true;   // 開機預設輪播；收到任何指令就停
static int      s_demoIdx = 0;
static uint32_t s_nextDemoAt = 0;

static void updateDemo(uint32_t now) {
  if (!s_demo || lcdCurActive || lcdQLen > 0 || now < s_nextDemoAt) return;
  const DemoStep &step = DEMO[s_demoIdx];
  s_demoIdx = (s_demoIdx + 1) % DEMO_LEN;
  if (step.text) {
    lcdSay(step.text, true, step.expr);
    s_nextDemoAt = now + 1000;
  } else {
    lcdSetMoodByName(step.expr);
    lcdClearText();
    s_nextDemoAt = now + 6000;
  }
}

static void handleJson(const char *data, size_t len) {
  JsonDocument doc;
  const DeserializationError err = deserializeJson(doc, data, len);
  if (err) {
    Serial.printf("JSON 解析失敗（%s）：%.*s\n", err.c_str(), (int)len, data);
    return;
  }
  const char *t = doc["t"] | "";
  s_demo = false;
  if (strcmp(t, "expr") == 0) {
    const char *expr = doc["expr"];
    if (expr != nullptr && !lcdSetMoodByName(expr)) Serial.printf("未知表情：%s\n", expr);
  } else if (strcmp(t, "say") == 0) {
    lcdSay(doc["text"] | "", doc["done"] | true, doc["expr"]);
  } else if (strcmp(t, "clear") == 0) {
    lcdClearText();
  } else {
    Serial.printf("未知訊息類型：%s\n", t);
  }
}

static void handleSerialLine(String line) {
  line.trim();
  if (line.length() == 0) return;

  if (line[0] == '{') {
    handleJson(line.c_str(), line.length());
    return;
  }
  if (line[0] == '/') {
    const String cmd = line.substring(1);
    if (cmd == "demo") {
      s_demo = true;
      s_nextDemoAt = 0;
      Serial.println(F("-> demo 模式"));
      return;
    }
    if (lcdSetMoodByName(cmd.c_str())) {
      s_demo = false;
      Serial.printf("-> expr = %s\n", cmd.c_str());
      return;
    }
    Serial.printf("未知指令：%s（可用 /neutral /idle /love /sad /sleepy /surprised /thinking /worried /dizzy /demo）\n",
                  line.c_str());
    return;
  }
  s_demo = false;
  lcdSay(line);
  Serial.printf("-> say \"%s\"\n", line.c_str());
}

static void pollSerial() {
  static String buf;
  while (Serial.available()) {
    const char c = (char)Serial.read();
    if (c == '\r' || c == '\n') {
      handleSerialLine(buf);
      buf = "";
    } else if (buf.length() < 512) {
      buf += c;
    }
  }
}

static void webSocketEvent(uint8_t num, WStype_t type, uint8_t *payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      Serial.printf("[%u] 電腦連上了\n", num);
      if (s_demo) {   // 電腦接手了：停掉輪播，清掉示範台詞，安靜地左顧右盼
        s_demo = false;
        lcdClearText();
        lcdSetMoodByName("idle");
      }
      break;
    case WStype_DISCONNECTED:
      Serial.printf("[%u] 斷線\n", num);
      break;
    case WStype_TEXT:
      handleJson((const char *)payload, length);
      break;
    default:
      break;
  }
}

void setup() {
  Serial.begin(MONITOR_SPEED);
  delay(1200);

  Serial.println();
  Serial.println(F("============================================================"));
  Serial.println(F(" ESP32 bring-up / Stage 5 : 黑貓臉（會動的眼睛 + 中文台詞）"));
  Serial.println(F("============================================================"));
  Serial.println(F(" 驗收順序："));
  Serial.println(F(" 1. 背光亮、黑底、淡藍圓眼出現，眼睛會自己四處看、會眨眼"));
  Serial.println(F(" 2. 開機後自動輪播 9 種情緒，台詞一行一行逐字出現"));
  Serial.println(F(" 3. Serial 打 /thinking 等指令或一句話，畫面跟著變"));
  Serial.println(F(" 4. 電腦連 WiFi 後用 WebSocket 送 JSON（格式見本段開頭註解）"));
  Serial.println(F(" 顏色不對或邊緣有雜線：lcd_faces.h 的 initR() 改 INITR_GREENTAB / INITR_REDTAB"));
  Serial.println(F(" 畫面上下顛倒：LCD_ROTATION 改成 3；有雜點：LCD_SPI_HZ 調低"));
  Serial.println(F("============================================================"));

  lcdInit();

  WiFi.softAP(WIFI_AP_SSID, WIFI_AP_PASSWORD);
  webSocket.begin();
  webSocket.onEvent(webSocketEvent);
  Serial.printf(" WiFi SSID: %s  密碼: %s\n", WIFI_AP_SSID, WIFI_AP_PASSWORD);
  Serial.printf(" WebSocket: ws://%s:%d/\n", WiFi.softAPIP().toString().c_str(), WS_PORT);
}

void loop() {
  webSocket.loop();
  pollSerial();

  const uint32_t now = millis();
  updateDemo(now);
  lcdUpdate(now);

  static uint32_t lastBeat = 0;
  if (now - lastBeat >= 1000) {
    lastBeat = now;
    String hb = "{\"t\":\"hb\",\"uptime_s\":" + String(now / 1000) + "}";
    webSocket.broadcastTXT(hb);
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
//  Step 9 — FSR + IMU over HTTP / WebSocket
// ============================================================
#elif APP_STAGE == 9
#include "telemetry_app.h"

// ============================================================
//  Step 10 — 無源蜂鳴器 MTARDALL112 PWM 測試
//  接線（3 腳驅動模組，2026-09-19 使用者確認實際腳位）：
//        VCC -> 3V3　GND -> GND　I-O(S) -> GPIO32
//  目的：驗證接線正確、PWM 音高控制會動；用耳朵就能判斷通不通。
// ============================================================
#elif APP_STAGE == 10

// 用 Arduino 內建的 tone()/noTone()（arduino-esp32 底層走 LEDC 硬體 PWM，
// 自動配置通道，不用自己管 channel），跨 arduino-esp32 版本相容性最好。
static void buzzerTone(uint32_t freqHz, uint32_t durationMs) {
  tone(PIN_BUZZER, freqHz, durationMs);
  delay(durationMs + 20);   // 多留一點空隙，音符之間才聽得出斷開
  noTone(PIN_BUZZER);
}

void setup() {
  Serial.begin(MONITOR_SPEED);
  delay(1200);
  Serial.println("\n=== Step 10: 無源蜂鳴器 PWM 測試 ===");
  Serial.printf("PIN_BUZZER = GPIO%d\n", PIN_BUZZER);
  Serial.println("先掃一段頻率（確認整個音域都聽得到），再重複播放一小段音階。");
  Serial.println("完全沒聲音 -> 先檢查接線；只有喀一聲、沒有音調 -> 可能買到的是有源蜂鳴器。");
  pinMode(PIN_BUZZER, OUTPUT);
}

void loop() {
  // 1) 頻率掃描：220Hz -> 2000Hz，整段都聽得到代表 PWM 驅動沒問題
  Serial.println("-- 頻率掃描 220Hz -> 2000Hz --");
  for (uint32_t f = 220; f <= 2000; f += 60) {
    buzzerTone(f, 25);
  }
  delay(500);

  // 2) 簡單音階 C4..C5，方便直接用耳朵判斷「是不是每個音都準時、都有聲音」
  static const uint32_t NOTES[] = {262, 294, 330, 349, 392, 440, 494, 523};
  Serial.println("-- 播放音階 C4..C5 --");
  for (uint32_t note : NOTES) {
    buzzerTone(note, 220);
  }
  delay(1200);
}

// ============================================================
//  Step 11 — INMP441 I2S 麥克風測試
//  接線：VDD -> 3V3　GND -> GND　L/R -> GND（單聲道/左聲道）
//        WS  -> GPIO13　SCK -> GPIO14　SD -> GPIO4
//  目的：驗證 I2S 接線正確、能連續讀到隨環境音大小變化的數值。
// ============================================================
#elif APP_STAGE == 11
#include <driver/i2s.h>
#include <math.h>

// 2026-09-19 找到問題根源：classic ESP32（不是 S3）的 I2S RX 週邊，設成
// I2S_CHANNEL_FMT_ONLY_LEFT / ONLY_RIGHT 這種單聲道模式時是已知有問題的
// 硬體/驅動限制，讀回來的資料整片是 0——這才是「接線明明沒問題、數字卻
// 一直顯示 0」的真正原因，不是你的接線或供電。繞過方式是設成立體聲
// I2S_CHANNEL_FMT_RIGHT_LEFT，兩個聲道都讀出來。
// INMP441 的 L/R 腳接 GND 時，datasheet 定義資料會出現在「左聲道」時槽，
// 但驅動程式實際把哪個時槽放進 buffer 的哪個位置，不同 IDF 版本可能不同，
// 與其我這邊用猜的，下面把兩個聲道的音量都印出來，用實測結果直接判定
// 哪一個是真的有資料的那個聲道，之後 Step 12 就照這裡量到的結果改。
static const int I2S_READ_FRAMES = 256;   // 1 frame = 左右各一個 int32
static int32_t s_i2sBuf[I2S_READ_FRAMES * 2];

static void i2sMicInit() {
  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate = MIC_SAMPLE_RATE_HZ;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;  // INMP441 實際輸出 24-bit，落在 32-bit 欄位的高位
  cfg.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;  // 立體聲，繞開 ONLY_LEFT 的已知問題
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count = 4;
  cfg.dma_buf_len = 256;
  cfg.use_apll = false;

  i2s_pin_config_t pins = {};
  pins.bck_io_num = PIN_MIC_SCK;
  pins.ws_io_num = PIN_MIC_WS;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = PIN_MIC_SD;

  esp_err_t err = i2s_driver_install(MIC_I2S_PORT, &cfg, 0, nullptr);
  if (err != ESP_OK) {
    Serial.printf("i2s_driver_install failed: %d\n", err);
    return;
  }
  err = i2s_set_pin(MIC_I2S_PORT, &pins);
  if (err != ESP_OK) {
    Serial.printf("i2s_set_pin failed: %d\n", err);
  }
}

void setup() {
  Serial.begin(MONITOR_SPEED);
  delay(1200);
  Serial.println("\n=== Step 11: INMP441 I2S 麥克風測試（立體聲診斷版）===");
  Serial.printf("SCK=GPIO%d  WS=GPIO%d  SD=GPIO%d  取樣率=%dHz\n",
    PIN_MIC_SCK, PIN_MIC_WS, PIN_MIC_SD, MIC_SAMPLE_RATE_HZ);
  Serial.println("下面同時印出兩個聲道的音量，對麥克風說話/拍手，看哪一個數字會動——");
  Serial.println("會動的那個才是真正接到麥克風資料的聲道。");
  i2sMicInit();
}

void loop() {
  size_t bytesRead = 0;
  esp_err_t err = i2s_read(MIC_I2S_PORT, (void *)s_i2sBuf, sizeof(s_i2sBuf), &bytesRead, portMAX_DELAY);
  if (err != ESP_OK || bytesRead == 0) {
    Serial.println("MIC_ch0_rms:0\tMIC_ch1_rms:0");
    delay(50);
    return;
  }

  const int frames = bytesRead / sizeof(int32_t) / 2;
  int64_t sumSq0 = 0, sumSq1 = 0;
  for (int i = 0; i < frames; i++) {
    // 右移 14 只是拿來換算成好比較的量級，不是校準過的 dBSPL。
    int32_t s0 = s_i2sBuf[i * 2]     >> 14;
    int32_t s1 = s_i2sBuf[i * 2 + 1] >> 14;
    sumSq0 += (int64_t)s0 * (int64_t)s0;
    sumSq1 += (int64_t)s1 * (int64_t)s1;
  }
  const double rms0 = sqrt((double)sumSq0 / frames);
  const double rms1 = sqrt((double)sumSq1 / frames);

  Serial.print(F("MIC_ch0_rms:")); Serial.print(rms0, 1);
  Serial.print('\t');
  Serial.print(F("MIC_ch1_rms:")); Serial.println(rms1, 1);
}

// ============================================================
//  Step 12 — INMP441 錄音，把原始 PCM 用 Serial 倒到電腦存成 .wav
//  接線跟 Step 11 完全一樣，不用重接。
//  這個階段的 Serial 鮑率改成 MIC_WAV_STREAM_BAUD（921600），跟其他階段
//  的 115200 不同——16kHz/16-bit 音訊一秒 32KB，115200 baud 塞不下。
//  開機先印 3 行文字說明，之後就是純二進位 PCM，不再夾雜任何文字
//  （文字跟二進位混在同一個 Serial 串流裡，電腦端會分不清楚邊界）。
//  電腦端用 tools/record_mic_wav.py 接收、存成 .wav。
// ============================================================
#elif APP_STAGE == 12
#include <driver/i2s.h>

// 2026-09-19：跟 Step 11 同一個根因——ONLY_LEFT 單聲道模式在 classic ESP32
// 上讀回來全部是 0，改成立體聲 I2S_CHANNEL_FMT_RIGHT_LEFT。實測結果
// （Step 11 印出來的 MIC_ch0_rms 有反應、MIC_ch1_rms 一直是 0）已經確認
// 資料在「聲道 0」（buffer 裡 i*2 那個位置），這裡就直接只取那個聲道，
// 輸出的 .wav 仍然是單聲道檔案——聲道 1 本來就是空的，存進去只是浪費空間。
static const int I2S_CHUNK_FRAMES = 256;   // 1 frame = 聲道0+聲道1 各一個 int32
static int32_t s_i2sRaw[I2S_CHUNK_FRAMES * 2];
static int16_t s_pcmOut[I2S_CHUNK_FRAMES];

static bool s_i2sReady = false;

static void i2sMicInit() {
  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate = MIC_SAMPLE_RATE_HZ;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  cfg.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;  // 立體聲，繞開 ONLY_LEFT 的已知問題
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  cfg.dma_buf_count = 4;
  cfg.dma_buf_len = 256;
  cfg.use_apll = false;

  i2s_pin_config_t pins = {};
  pins.bck_io_num = PIN_MIC_SCK;
  pins.ws_io_num = PIN_MIC_WS;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = PIN_MIC_SD;

  // 這兩個呼叫的回傳值一定要檢查：一旦裝置裝失敗，下面 loop() 裡的
  // i2s_read(..., portMAX_DELAY) 會永遠等不到資料、卡死不回傳——
  // 症狀就是「電腦端完全收不到任何 byte，連垃圾資料都沒有」，
  // 之前的版本沒印錯誤訊息，等於這種情況會無聲無息卡住，不好排查。
  esp_err_t err = i2s_driver_install(MIC_I2S_PORT, &cfg, 0, nullptr);
  if (err != ESP_OK) {
    Serial.printf("ERROR i2s_driver_install failed: %d\n", err);
    return;
  }
  err = i2s_set_pin(MIC_I2S_PORT, &pins);
  if (err != ESP_OK) {
    Serial.printf("ERROR i2s_set_pin failed: %d\n", err);
    return;
  }
  s_i2sReady = true;
}

void setup() {
  Serial.begin(MIC_WAV_STREAM_BAUD);
  delay(500);
  // 剛好 3 行，電腦端腳本靠這個固定行數判斷「文字說明讀完了、接下來是二進位」。
  // 如果下面 i2sMicInit() 失敗，會多印一行 ERROR——電腦端腳本此時會把這行
  // 誤當成第 3 行標頭讀掉，所以錯誤訊息务必用 Serial Monitor（不是 python
  // 腳本）去看，見 platformio.ini 這個 env 的 monitor_speed=921600。
  Serial.println("=== Step 12: I2S mic raw PCM over Serial ===");
  Serial.printf("sample_rate=%d bits=16 channels=1 baud=%d\n", MIC_SAMPLE_RATE_HZ, MIC_WAV_STREAM_BAUD);
  Serial.println("3 秒後開始輸出純二進位 PCM，電腦端請用 tools/record_mic_wav.py 接收。");
  delay(3000);
  i2sMicInit();
  if (!s_i2sReady) {
    Serial.println("i2s 初始化失敗，不會有任何 PCM 輸出，請用 Serial Monitor 檢查上面的 ERROR 訊息。");
  }
}

void loop() {
  size_t bytesRead = 0;
  i2s_read(MIC_I2S_PORT, (void *)s_i2sRaw, sizeof(s_i2sRaw), &bytesRead, portMAX_DELAY);
  const int frames = bytesRead / sizeof(int32_t) / 2;
  for (int i = 0; i < frames; i++) {
    // 只取聲道 0（Step 11 實測確認是有資料的那個），聲道 1 直接丟棄。
    // 跟 Step 11 一樣的量級換算，但這裡是拿來組成真正的 16-bit PCM 樣本，
    // 所以要做溢位保護（clamp），避免大聲時數值繞回負數變成爆音雜訊。
    // 位移量選比較保守的值，寧可錄出來偏小聲、也不要削峰失真；真正的
    // 音量正規化交給電腦端 record_mic_wav.py 事後自動放大，見該檔案。
    int32_t v = s_i2sRaw[i * 2] >> 13;
    if (v > 32767) v = 32767;
    if (v < -32768) v = -32768;
    s_pcmOut[i] = (int16_t)v;
  }
  Serial.write((uint8_t *)s_pcmOut, frames * sizeof(int16_t));
}

// ============================================================
//  Step 13 — 整合 build：LCD(5) + FSR/IMU/WS(9) + 蜂鳴器(10) + 麥克風(11/12)
//  併成一份韌體，對應 docs/api.html §① 定案的 WebSocket 合約（取代原本
//  規劃但從未實作的 USB Serial 通道）。實作在 include/companion_app.h、
//  include/lcd_faces.h、include/mic_stream.h，這裡只負責 include 進來。
//
//  ⚠️ 還沒有實機驗證過，見 companion_app.h 檔頭的警告。Step 6（原本規劃
//  的 FSR+IMU+LCD 整合）就此由 Step 13 取代，不再單獨實作 Step 6。
// ============================================================
#elif APP_STAGE == 13
#include "companion_app.h"

#else

void setup() {
  Serial.begin(MONITOR_SPEED);
  delay(1200);
  Serial.printf("\nAPP_STAGE=%d 尚未實作。\n", APP_STAGE);
  Serial.println("目前已實作：s1_serial、s2_fsr1、s3_fsr2、s4_imu、s5_lcd、s7_wifi_http、s8_wifi_ws、s9_wifi_sensors、s10_buzzer、s11_mic、s12_mic_wav、s13_companion。");
}

void loop() {
  delay(1000);
}

#endif
