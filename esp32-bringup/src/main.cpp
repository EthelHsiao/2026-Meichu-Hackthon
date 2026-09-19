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
//  Step 5 — LCD 黑貓臉：一直在動的大圓眼 + 一行一行出現的中文台詞
//  接線：8 腳小紅板（A 型），使用者已目視確認（2026-09-18）：
//    VCC->3V3  GND->GND  SCL->D18  SDA->D23  RES->D25  DC->D26  CS->D27  BLK->3V3
//
//  畫面（橫放 160x128）：
//    ┌──────────────────┐
//    |    (●)    (●)    |  ← 淡藍圓眼 + 黑瞳孔：會四處看、會眨眼、隨情緒變形
//    |        w         |  ← 小嘴巴，說話時一開一合（idle / dizzy 沒有嘴巴）
//    |   嗨，我在這裡   |  ← 台詞只有一行：逐字出現，這行講完停一下就消失，換下一行
//    └──────────────────┘
//
//  眼睛不是「換一張圖」：每個情緒只是一組目標參數（眼睛大小、瞳孔大小、
//  上眼皮位置與斜度），每一幀都往目標值平滑靠近，換情緒是連續變形過去的；
//  再疊上隨機視線、呼吸、眨眼，眼睛就一直是活的。dizzy 的螺旋眼跟圓眼差太多，
//  切換時會先眨一下眼，在閉眼那一瞬間換掉。
//
//  整個畫面先畫在記憶體畫布（GFXcanvas16），再一次推到螢幕，不會閃爍。
//  台詞用 include/font_tc12.h（Fusion Pixel 12px 繁中，常用 5401 字 + 標點 + ASCII），
//  字型由 tools/make_font_tc12.py 產生；罕用字會顯示成空白。
//
//  通訊：WiFi SoftAP + WebSocket（ws://192.168.4.1:81/），格式見
//  docs/data_structures.md ①。Serial Monitor 也吃同樣的 JSON，沒連 WiFi 也能測：
//    {"t":"expr","expr":"thinking"}                  → 換情緒
//    {"t":"say","expr":"sad","text":"你要走了嗎"}     → 排一句台詞（輪到它時才換情緒）
//    {"t":"say","text":"嗯…讓我","done":false}        → 串流：同一句陸續補字…
//    {"t":"say","text":"想想"}                        →   …done 省略 = true，這句結束
//    {"t":"clear"}                                   → 清掉台詞和佇列
//  Serial 捷徑：/idle /thinking …換情緒、/demo 輪播、其他文字直接當一句台詞。
// ============================================================
#elif APP_STAGE == 5
#include <SPI.h>
#include <WiFi.h>
#include <WebSocketsServer.h>
#include <ArduinoJson.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <U8g2_for_Adafruit_GFX.h>
#include "font_tc12.h"

Adafruit_ST7735 tft(PIN_LCD_CS, PIN_LCD_DC, PIN_LCD_RST);
WebSocketsServer webSocket(WS_PORT);
U8G2_FOR_ADAFRUIT_GFX u8g2;

static const uint8_t  LCD_ROTATION = 1;          // 1 = 橫放；畫面上下顛倒就改成 3
static const uint32_t LCD_SPI_HZ   = 27000000;   // 畫面有雜點就降到 16000000
static const uint32_t FRAME_MS     = 33;         // 約 30 fps

static const uint16_t COLOR_BG  = ST77XX_BLACK;
static const uint16_t COLOR_FG  = ST77XX_WHITE;  // 台詞
static const uint16_t COLOR_EYE = 0xBF3F;        // 淡藍 (191,230,255)，眼睛和嘴巴共用

// ---- 版面（以 160x128 橫放為準）----
static const int EYE_Y     = 44;    // 眼睛中心 y
static const int EYE_DX    = 37;    // 眼睛離中線距離
static const int MOUTH_Y   = 82;    // 嘴巴中心 y
static const int TEXT_TOP  = 98;    // 台詞區上緣：臉再怎麼動都不會畫到這條線以下
static const int TEXT_BASE = 117;   // 台詞 baseline

static int s_w = 0, s_h = 0, s_cx = 0;
static GFXcanvas16 *s_canvas = nullptr;

// ============================================================
//  情緒：一組眼睛目標值 + 一種「視線習慣」
//  名稱與順序要跟 ai-pc-agent/protocol.py 的 EXPRESSIONS 一致
// ============================================================
enum Mood { MOOD_NEUTRAL, MOOD_IDLE, MOOD_LOVE, MOOD_SAD, MOOD_SLEEPY, MOOD_SURPRISED,
            MOOD_THINKING, MOOD_WORRIED, MOOD_DIZZY, MOOD_COUNT };
static const char *MOOD_NAMES[MOOD_COUNT] = {"neutral", "idle", "love", "sad", "sleepy",
                                             "surprised", "thinking", "worried", "dizzy"};

struct MoodStyle {
  float eyeR;        // 眼睛半徑
  float pupilR;      // 瞳孔半徑：大 = 溫柔、小 = 驚訝/緊張
  float lidTop;      // 上眼皮蓋住多少 0~1
  float lidTilt;     // 上眼皮斜度：+ 外側低（難過/擔心）
  float squintR;     // 右眼額外多瞇多少（思考時一眼大一眼小）
  uint16_t lookMinMs, lookMaxMs;   // 多久換一次視線
  float lookX, lookY;              // 視線亂飄的範圍（-1~1）
  float biasX, biasY;              // 視線偏好的方向
  float gazeTau;                   // 眼球移動時間常數（ms），小 = 動得快
};

static const MoodStyle MOOD_STYLE[MOOD_COUNT] = {
  // eyeR pupil lidT  tilt  sqR   minMs maxMs lookX lookY biasX  biasY  tau
  {  27,  20,  0.00, 0.0,  0.00,  900, 3000, 1.0,  0.6,  0.0,   0.0,   70 },  // neutral
  {  27,  20,  0.00, 0.0,  0.00, 1400, 3000, 1.0,  0.15, 0.0,   0.0,  110 },  // idle：左顧右盼（見 updateGazeTarget）
  {  28,  23,  0.00, 0.0,  0.00, 1600, 3600, 0.4,  0.25, 0.0,   0.0,  160 },  // love
  {  26,  21,  0.30, 0.8,  0.00, 1800, 3800, 0.5,  0.2,  0.0,   0.7,  140 },  // sad
  {  26,  20,  0.55, 0.0,  0.00, 2500, 5000, 0.4,  0.2,  0.0,   0.4,  280 },  // sleepy
  {  30,  14,  0.00, 0.0,  0.00, 1500, 3000, 0.15, 0.15, 0.0,   0.0,   45 },  // surprised
  {  27,  19,  0.10, 0.0,  0.18, 1300, 2600, 0.3,  0.3,  0.75, -0.75, 120 },  // thinking
  {  27,  17,  0.20, 0.6,  0.00,  350, 1000, 1.0,  0.4,  0.0,   0.1,   45 },  // worried
  {  27,  20,  0.00, 0.0,  0.00, 1000, 1000, 0.0,  0.0,  0.0,   0.0,   70 },  // dizzy：畫螺旋，不用這些值
};

static int moodFromName(const char *name) {
  for (int i = 0; i < MOOD_COUNT; i++) {
    if (strcmp(name, MOOD_NAMES[i]) == 0) return i;
  }
  // 舊的表情名稱：目前 protocol.py / MI300 還在用，先當 neutral 顯示（w 嘴本來就是笑臉）
  if (strcmp(name, "happy") == 0 || strcmp(name, "joy") == 0) return MOOD_NEUTRAL;
  return -1;
}

// 眼睛現在的樣子（每幀往目標靠近）
struct EyeState { float eyeR, pupilR, lidTop, lidTilt, squintR; };
static EyeState s_eye, s_eyeTarget;
static Mood     s_mood = MOOD_NEUTRAL;
static bool     s_showSpiral = false;    // 畫面上現在是不是螺旋眼（眨眼中途才切換）
static float    s_gazeX = 0, s_gazeY = 0, s_gazeTX = 0, s_gazeTY = 0;   // -1~1
static float    s_lookSide = 1;
static uint32_t s_nextLookAt = 0;
static uint32_t s_blinkAt = 0, s_nextBlinkAt = 0;
static bool     s_doubleBlink = false;
static bool     s_talking = false;       // 台詞正在逐字出現

static void setMood(Mood m) {
  s_mood = m;
  const MoodStyle &st = MOOD_STYLE[m];
  s_eyeTarget = {st.eyeR, st.pupilR, st.lidTop, st.lidTilt, st.squintR};
  s_nextLookAt = 0;   // 換情緒時馬上換個視線，看起來像有反應
}

static float frand() { return (esp_random() & 0xFFFF) / 65535.0f; }
static int16_t px(float v) { return (int16_t)lroundf(v); }

// 指數平滑：不管幀率多少，都在 tau 毫秒左右走完約 63%
static float approach(float cur, float target, float dtMs, float tauMs) {
  return cur + (target - cur) * (1.0f - expf(-dtMs / tauMs));
}

// ---- 視線：隨機挑下一個要看的點，眼球平滑移過去 ----
static void updateGazeTarget(uint32_t now) {
  if (now < s_nextLookAt) return;
  const MoodStyle &st = MOOD_STYLE[s_mood];
  s_nextLookAt = now + st.lookMinMs + esp_random() % (st.lookMaxMs - st.lookMinMs + 1);

  if (s_mood == MOOD_IDLE) {   // 左顧右盼：左右輪流看
    s_lookSide = -s_lookSide;
    s_gazeTX = s_lookSide * (0.7f + 0.3f * frand());
    s_gazeTY = (frand() * 2 - 1) * st.lookY;
    return;
  }
  if (s_mood == MOOD_THINKING && frand() < 0.25f) s_lookSide = -s_lookSide;   // 左上、右上輪流看
  float bx = st.biasX * s_lookSide, by = st.biasY;
  float rx = st.lookX, ry = st.lookY;
  if (s_talking) { bx = 0; by = 0; rx *= 0.3f; ry *= 0.3f; }   // 說話時看著使用者

  if (frand() < 0.35f) {   // 常常回到偏好位置，才不會一直亂飄
    s_gazeTX = bx;
    s_gazeTY = by;
    return;
  }
  s_gazeTX = constrain(bx + (frand() * 2 - 1) * rx, -1.0f, 1.0f);
  s_gazeTY = constrain(by + (frand() * 2 - 1) * ry, -1.0f, 1.0f);
}

// ---- 眨眼：回傳 0（張開）~ 1（閉上）----
static float blinkAmount(uint32_t now) {
  const bool sleepy = s_mood == MOOD_SLEEPY;
  const uint32_t closeMs = sleepy ? 220 : 70, holdMs = sleepy ? 180 : 40, openMs = sleepy ? 320 : 100;
  if (s_blinkAt == 0) {
    // 畫面上的形狀（圓眼／螺旋）跟情緒對不上就馬上眨一下，在閉眼時換掉；螺旋眼平常不自己眨
    const bool needSwap = s_showSpiral != (s_mood == MOOD_DIZZY);
    if (!needSwap && (now < s_nextBlinkAt || s_showSpiral)) return 0;
    s_blinkAt = now;
  }
  const uint32_t t = now - s_blinkAt;
  if (t < closeMs) return (float)t / closeMs;
  if (t < closeMs + holdMs) return 1;
  if (t < closeMs + holdMs + openMs) return 1 - (float)(t - closeMs - holdMs) / openMs;

  s_blinkAt = 0;   // 眨完了，排下一次；偶爾連眨兩下
  if (!s_doubleBlink && frand() < 0.15f) {
    s_doubleBlink = true;
    s_nextBlinkAt = now + 120;
  } else {
    s_doubleBlink = false;
    s_nextBlinkAt = now + (s_mood == MOOD_SURPRISED ? 4000 : 2200) + esp_random() % 3500;
  }
  return 0;
}

// ---- 畫一隻眼睛：淡藍圓 → 黑瞳孔 → 上眼皮 ----
static void drawEye(GFXcanvas16 &c, float cx, float cy, bool isLeft, float blink, float breath) {
  const EyeState &e = s_eye;
  const float R  = e.eyeR + breath;
  const float ex = cx + s_gazeX * 5, ey = cy + s_gazeY * 4;   // 整顆眼睛也跟著視線偏一點
  c.fillCircle(px(ex), px(ey), px(R), COLOR_EYE);

  const float maxOff = max(0.0f, R - e.pupilR - 4);   // 瞳孔不能跑出淡藍圓
  c.fillCircle(px(ex + s_gazeX * maxOff), px(ey + s_gazeY * maxOff), px(e.pupilR), COLOR_BG);

  // 上眼皮：黑色多邊形從上面蓋下來，可以歪
  float lid = e.lidTop + (isLeft ? 0 : e.squintR);
  lid = min(1.0f, lid + (1 - lid) * blink);   // 眨眼 = 眼皮蓋到底
  const float top  = ey - R - 3;
  const float lidY = ey - R + 2 * R * lid;
  const float tilt = e.lidTilt * R * 0.55f * (1 - blink);   // 閉眼時拉平
  const float x0 = ex - R - 3, x1 = ex + R + 3;
  const float yL = lidY + (isLeft ? tilt : -tilt);           // 左眼的外側在左邊
  const float yR = lidY + (isLeft ? -tilt : tilt);
  if (max(yL, yR) > top) {
    c.fillTriangle(px(x0), px(top), px(x1), px(top), px(x0), px(yL), COLOR_BG);
    c.fillTriangle(px(x1), px(top), px(x1), px(yR), px(x0), px(yL), COLOR_BG);
  }
}

// ---- dizzy 的螺旋眼：沿著螺旋線蓋一串小圓點，就是一條粗線 ----
static void drawSpiral(GFXcanvas16 &c, float cx, float cy, float rot, float dir, float scale) {
  for (int i = 0; i <= 220; i++) {
    const float t = i / 220.0f;
    const float a = dir * t * 5 * PI + rot;
    const float r = (2 + t * 23) * scale;
    c.fillCircle(px(cx + cosf(a) * r), px(cy + sinf(a) * r), 2, COLOR_EYE);
  }
}

// ---- 嘴巴：平常是小 w，說話時一開一合 ----
static void drawMouth(GFXcanvas16 &c, int x, int y, uint32_t now) {
  if (s_talking && (now / 130) % 2 == 0) {
    c.fillRoundRect(x - 3, y - 3, 7, 8, 3, COLOR_EYE);
    return;
  }
  for (int r = 3; r <= 4; r++) {   // 疊兩圈 = 2px 粗；drawCircleHelper 4|8 = 下半圓
    c.drawCircleHelper(x - 4, y - 1, r, 4 | 8, COLOR_EYE);
    c.drawCircleHelper(x + 4, y - 1, r, 4 | 8, COLOR_EYE);
  }
}

// ============================================================
//  台詞：只有一行。逐字出現，這行寫滿或這句講完就停一下，然後整行消失換下一行
//  串流時同一句會陸續補字（done=false），補到 done=true 才算講完
// ============================================================
static const int      TEXT_MAX_W       = 148;    // 一行最寬（左右各留 6px）
static const int      TEXT_HANG_W      = 156;    // 行尾標點可以稍微凸出去，不要自己跑到下一行開頭
static const uint32_t CHAR_MS          = 85;     // 打字速度（中文）
static const uint32_t CHAR_MS_ASCII    = 55;     // 打字速度（英文、數字）
static const uint32_t LINE_HOLD_MS     = 900;    // 一行寫滿，停多久再換下一行
static const uint32_t SENTENCE_HOLD_MS = 1500;   // 一句講完，停多久才換下一句
static const uint32_t TEXT_LINGER_MS   = 8000;   // 講完後沒有下一句，最後一行留多久才消失
static const uint32_t STREAM_TIMEOUT_MS = 5000;  // 串流中的句子多久沒收到新字，就當它講完（done 那則可能掉了）
static const int      SENTENCE_MAX_BYTES = 600;  // 一句最多收多少 byte（約 200 個中文字），超過的丟掉保護記憶體

struct Sentence { String text; bool done; int8_t mood; };   // mood = -1：不換情緒
static const int QUEUE_MAX = 6;
static Sentence s_queue[QUEUE_MAX];
static int s_qHead = 0, s_qLen = 0;

static Sentence s_cur;
static bool     s_curActive = false;
static int      s_pos = 0;               // 已經顯示到第幾個 byte
static String   s_line;                  // 畫面上那一行
static bool     s_lineDone = false;      // 這一行講完了，停一下就換
static bool     s_sentenceEnded = false; // 這句最後一行已經開始停頓
static uint32_t s_nextCharAt = 0, s_lingerUntil = 0, s_lastChunkAt = 0;

static int utf8Len(uint8_t lead) {
  if (lead < 0x80) return 1;
  if ((lead >> 5) == 0x6) return 2;
  if ((lead >> 4) == 0xE) return 3;
  if ((lead >> 3) == 0x1E) return 4;
  return 1;
}

static bool isClosingPunct(const String &ch) {
  static const char *const PUNCT[] = {"，", "。", "！", "？", "、", "…", "；", "：", "」", "』", "）", "～",
                                      ",", ".", "!", "?", ";", ":", ")"};
  for (const char *p : PUNCT) {
    if (ch == p) return true;
  }
  return false;
}

// 從 i 開始的英文單字（判斷整個單字放不放得下）
static String asciiWordAt(const String &s, int i) {
  int j = i;
  while (j < (int)s.length() && (uint8_t)s[j] < 0x80 && s[j] != ' ' && s[j] != '\n') j++;
  return s.substring(i, j);
}

static int textWidth(const String &s) { return u8g2.getUTF8Width(s.c_str()); }

static void appendCapped(String &dst, const String &text) {
  if ((int)(dst.length() + text.length()) <= SENTENCE_MAX_BYTES) {
    dst += text;
    return;
  }
  int keep = SENTENCE_MAX_BYTES - dst.length();
  while (keep > 0 && ((uint8_t)text[keep] & 0xC0) == 0x80) keep--;   // 不要切在中文字中間
  if (keep > 0) dst += text.substring(0, keep);
  Serial.println(F("台詞太長，後面的丟掉"));
}

static void queueSay(const String &text, bool done, int mood) {
  s_lastChunkAt = millis();
  // 串流：最後一句還沒講完，就接在它後面
  Sentence *open = nullptr;
  if (s_qLen > 0) {
    Sentence &last = s_queue[(s_qHead + s_qLen - 1) % QUEUE_MAX];
    if (!last.done) open = &last;
  } else if (s_curActive && !s_cur.done) {
    open = &s_cur;
  }
  // 串流只有第一段帶 expr；還開著的句子又收到帶 expr 的訊息，代表上一句的 done 掉了、這是新的一句
  if (open && mood >= 0) {
    open->done = true;
    open = nullptr;
  }
  if (open) {
    appendCapped(open->text, text);
    open->done = done;
    return;
  }
  if (s_qLen == QUEUE_MAX) {
    Serial.println(F("台詞佇列滿了，丟掉最舊的一句"));
    s_qHead = (s_qHead + 1) % QUEUE_MAX;
    s_qLen--;
  }
  Sentence &slot = s_queue[(s_qHead + s_qLen) % QUEUE_MAX];
  slot = {"", done, (int8_t)mood};
  appendCapped(slot.text, text);
  s_qLen++;
}

static void clearSpeech() {
  for (int i = 0; i < QUEUE_MAX; i++) s_queue[i] = Sentence();
  s_qHead = s_qLen = 0;
  s_cur = Sentence();
  s_curActive = false;
  s_pos = 0;
  s_line = "";
  s_lineDone = false;
}

// 這一行講完：停一下，下次要出字時整行消失
static void endLine(uint32_t now, uint32_t holdMs) {
  s_lineDone = true;
  s_nextCharAt = now + holdMs;
}

// 顯示下一個字
static void revealNext(uint32_t now) {
  const String &s = s_cur.text;
  if (s_lineDone) {   // 上一行停夠了，消失
    s_line = "";
    s_lineDone = false;
  }

  const uint8_t lead = s[s_pos];
  const int n = utf8Len(lead);
  if (s_pos + n > (int)s.length()) {   // 中文字的 byte 還沒收齊（串流切在字中間）
    if (s_cur.done) s_pos = s.length();
    return;
  }
  const String ch = s.substring(s_pos, s_pos + n);

  if (lead == '\n') {
    s_pos += n;
    if (s_line.length() > 0) endLine(now, LINE_HOLD_MS);
    return;
  }
  if (lead == ' ' && s_line.length() == 0) {   // 行首空白不顯示
    s_pos += n;
    return;
  }

  // 放不下就先把這行結束；英文看整個單字，行尾標點可以稍微凸出去
  const bool wordStart = lead < 0x80 && lead != ' ' &&
                         (s_pos == 0 || s[s_pos - 1] == ' ' || (uint8_t)s[s_pos - 1] >= 0x80);   // 空白或中文後面都算新單字
  const String next = wordStart ? asciiWordAt(s, s_pos) : ch;
  const int limit = isClosingPunct(ch) ? TEXT_HANG_W : TEXT_MAX_W;
  if (s_line.length() > 0 && textWidth(s_line + next) > limit) {
    endLine(now, LINE_HOLD_MS);
    return;
  }

  s_pos += n;
  s_line += ch;
  const bool stop  = ch == "。" || ch == "！" || ch == "？" || ch == "…" || lead == '.' || lead == '!' || lead == '?';
  const bool pause = ch == "，" || ch == "、" || lead == ',';
  s_nextCharAt = now + (stop ? 260 : pause ? 140 : lead < 0x80 ? CHAR_MS_ASCII : CHAR_MS);
}

static void updateSpeech(uint32_t now) {
  if (!s_curActive) {
    if (s_qLen == 0) {
      if (s_line.length() > 0 && now >= s_lingerUntil) s_line = "";   // 講完很久了，讓最後一行消失
      return;
    }
    s_cur = s_queue[s_qHead];
    s_queue[s_qHead] = Sentence();
    s_qHead = (s_qHead + 1) % QUEUE_MAX;
    s_qLen--;
    s_curActive = true;
    s_pos = 0;
    s_line = "";
    s_lineDone = false;
    s_sentenceEnded = false;
    s_nextCharAt = now;
    if (s_cur.mood >= 0) setMood((Mood)s_cur.mood);
  }

  if (now < s_nextCharAt) return;
  if (s_pos < (int)s_cur.text.length()) {
    revealNext(now);
    return;
  }
  if (!s_cur.done) {         // 串流還沒講完，等下一段；太久沒收到就當它講完
    if (now - s_lastChunkAt < STREAM_TIMEOUT_MS) return;
    Serial.println(F("串流太久沒收到新字，這句當作講完"));
    s_cur.done = true;
  }
  if (!s_sentenceEnded) {    // 這句剛講完：最後一行停久一點
    s_sentenceEnded = true;
    endLine(now, SENTENCE_HOLD_MS);
    return;
  }
  s_curActive = false;       // 停夠了：有下一句就換（換的時候這行才消失），沒有就留著一陣子
  s_lingerUntil = now + TEXT_LINGER_MS;
}

// ---- 一幀：更新參數 → 臉 → 台詞 → 一次推上螢幕 ----
static void renderFrame(uint32_t now) {
  if (!s_canvas->getBuffer()) return;   // 畫布配置失敗（setup 已經在螢幕上顯示錯誤）
  static uint32_t lastFrame = 0;
  if (now - lastFrame < FRAME_MS) return;
  const float dt = min<uint32_t>(now - lastFrame, 100);
  lastFrame = now;

  const float tau = 110;   // 換情緒時眼睛變形的速度
  s_eye.eyeR    = approach(s_eye.eyeR,    s_eyeTarget.eyeR,    dt, tau);
  s_eye.pupilR  = approach(s_eye.pupilR,  s_eyeTarget.pupilR,  dt, tau);
  s_eye.lidTop  = approach(s_eye.lidTop,  s_eyeTarget.lidTop,  dt, tau);
  s_eye.lidTilt = approach(s_eye.lidTilt, s_eyeTarget.lidTilt, dt, tau);
  s_eye.squintR = approach(s_eye.squintR, s_eyeTarget.squintR, dt, tau);

  updateGazeTarget(now);
  const float gazeTau = MOOD_STYLE[s_mood].gazeTau;
  s_gazeX = approach(s_gazeX, s_gazeTX, dt, gazeTau);
  s_gazeY = approach(s_gazeY, s_gazeTY, dt, gazeTau);

  // 呼吸：整張臉慢慢上下浮動、眼睛微微縮放；love 輕輕左右晃、dizzy 晃比較大
  const float phase  = now * (TWO_PI / 3200.0f);
  const float breath = sinf(phase) * 0.7f;
  const float bob    = sinf(phase) * 1.4f;
  float sway = 0;
  if (s_mood == MOOD_LOVE)  sway = sinf(now * (TWO_PI / 2400.0f)) * 3;
  if (s_mood == MOOD_DIZZY) sway = sinf(now * (TWO_PI / 1600.0f)) * 4;

  const float blink = blinkAmount(now);
  if (blink > 0.95f) s_showSpiral = s_mood == MOOD_DIZZY;   // 閉眼那一瞬間換形狀

  GFXcanvas16 &c = *s_canvas;
  c.fillScreen(COLOR_BG);
  const float lx = s_cx - EYE_DX + sway, rx = s_cx + EYE_DX + sway, ey = EYE_Y + bob;
  if (s_showSpiral) {
    const float rot = now / 260.0f;
    drawSpiral(c, lx, ey, rot, 1, 1 - blink);
    drawSpiral(c, rx, ey, -rot, -1, 1 - blink);
  } else {
    drawEye(c, lx, ey, true, blink, breath);
    drawEye(c, rx, ey, false, blink, breath);
  }
  if (s_mood != MOOD_IDLE && s_mood != MOOD_DIZZY) {
    drawMouth(c, px(s_cx + sway + s_gazeX * 2), px(MOUTH_Y + bob), now);
  }

  // 台詞區先整條塗黑，臉怎麼動都不會蓋到字
  c.fillRect(0, TEXT_TOP, s_w, s_h - TEXT_TOP, COLOR_BG);
  if (s_line.length() > 0) {
    u8g2.drawUTF8((s_w - textWidth(s_line)) / 2, TEXT_BASE, s_line.c_str());
  }
  tft.drawRGBBitmap(0, 0, c.getBuffer(), c.width(), c.height());
}

// ============================================================
//  指令：WebSocket 和 Serial 都走這裡
// ============================================================
struct DemoStep { Mood mood; const char *text; };   // text = nullptr：只換表情、安靜一陣子
static const DemoStep DEMO[] = {
  {MOOD_NEUTRAL,   "嗨，我在這裡陪你。"},
  {MOOD_IDLE,      nullptr},
  {MOOD_THINKING,  "嗯…讓我想想這個 bug 是從哪裡來的"},
  {MOOD_WORRIED,   "這個錯誤已經卡 40 分鐘了，要不要換個方法？"},
  {MOOD_SURPRISED, "哇！居然一次就編譯成功了！"},
  {MOOD_LOVE,      "你今天好認真，我好喜歡看你寫程式"},
  {MOOD_SAD,       "你要走了嗎…再陪我一下下好不好"},
  {MOOD_SLEEPY,    "好睏…已經凌晨兩點了，明天再寫吧"},
  {MOOD_DIZZY,     "被你搖得頭好暈…世界在轉圈圈"},
};
static const int DEMO_LEN = sizeof(DEMO) / sizeof(DEMO[0]);

static bool     s_demo = true;   // 開機預設輪播；收到任何指令就停
static int      s_demoIdx = 0;
static uint32_t s_nextDemoAt = 0;

static void updateDemo(uint32_t now) {
  if (!s_demo || s_curActive || s_qLen > 0 || now < s_nextDemoAt) return;
  const DemoStep &step = DEMO[s_demoIdx];
  s_demoIdx = (s_demoIdx + 1) % DEMO_LEN;
  if (step.text) {
    queueSay(step.text, true, step.mood);
    s_nextDemoAt = now + 1000;
  } else {
    setMood(step.mood);
    s_line = "";
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
  const char *exprName = doc["expr"] | "";
  int mood = -1;
  if (*exprName) {
    mood = moodFromName(exprName);
    if (mood < 0) Serial.printf("未知表情：%s\n", exprName);
  }

  s_demo = false;
  if (strcmp(t, "expr") == 0) {
    if (mood >= 0) setMood((Mood)mood);
  } else if (strcmp(t, "say") == 0) {
    queueSay(doc["text"] | "", doc["done"] | true, mood);
  } else if (strcmp(t, "clear") == 0) {
    clearSpeech();
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
    const int m = moodFromName(cmd.c_str());
    if (m >= 0) {
      s_demo = false;
      setMood((Mood)m);
      Serial.printf("-> expr = %s\n", MOOD_NAMES[m]);
      return;
    }
    Serial.printf("未知指令：%s（可用 /neutral /idle /love /sad /sleepy /surprised /thinking /worried /dizzy /demo）\n",
                  line.c_str());
    return;
  }
  s_demo = false;
  queueSay(line, true, -1);
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
        clearSpeech();
        setMood(MOOD_IDLE);
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
  Serial.println(F(" 顏色不對或邊緣有雜線：initR() 改 INITR_GREENTAB / INITR_REDTAB"));
  Serial.println(F(" 畫面上下顛倒：LCD_ROTATION 改成 3；有雜點：LCD_SPI_HZ 調低"));
  Serial.println(F("============================================================"));

  tft.initR(INITR_BLACKTAB);
  tft.setSPISpeed(LCD_SPI_HZ);
  tft.setRotation(LCD_ROTATION);
  s_w  = tft.width();
  s_h  = tft.height();
  s_cx = s_w / 2;
  tft.fillScreen(COLOR_BG);

  s_canvas = new GFXcanvas16(s_w, s_h);
  if (!s_canvas->getBuffer()) {   // 記憶體不夠：顯示錯誤就好，不要讓後面畫到空指標
    Serial.println(F("!! 畫布記憶體配置失敗，臉部停用"));
    tft.setTextColor(ST77XX_RED);
    tft.setCursor(4, 60);
    tft.print("canvas alloc failed");
  }
  u8g2.begin(*s_canvas);
  u8g2.setFont(u8g2_font_tc12);
  u8g2.setFontMode(1);   // 透明背景
  u8g2.setForegroundColor(COLOR_FG);

  setMood(MOOD_NEUTRAL);
  s_eye = s_eyeTarget;
  s_nextBlinkAt = millis() + 1500;

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
  updateSpeech(now);
  s_talking = s_curActive && s_pos < (int)s_cur.text.length() && !s_lineDone;
  renderFrame(now);

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
