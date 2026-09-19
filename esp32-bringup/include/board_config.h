#pragma once
// ============================================================
//  board_config.h — 單一事實來源（single source of truth）
//
//  接線表（docs/wiring.md）、接線圖、所有 sketch 都要跟這份檔案對齊。
//  標記說明：
//    [CONFIRMED] 使用者親口確認，或由實機／datasheet 佐證
//    [CANDIDATE] 尚未由實機確認的推測，不可當成量測結果
//    TBD         完全沒資料
//
//  2026-09-15 更新：使用者確認零件清單為
//    ESP32 DevKit V1 ×1 / FSR402 ×2 / MPU6050 ×1 / 1.8" TFT LCD ×1
//    電阻 10kΩ ×10、4.7kΩ ×10、47kΩ ×10
//  2026-09-18 更新：新增 WiFi / 電腦通訊參數（Step 7 / Step 8）
// ============================================================

// ------------------------------------------------------------
//  1. 板型（Step 0）
// ------------------------------------------------------------
// 使用者確認：ESP32 DevKit V1。屬 classic ESP32-WROOM-32 系列，
// 下方所有 GPIO 配置以此為前提。
// 仍需在 Stage 1 驗證：開機 banner 的 ESP.getChipModel()
//   印出 "ESP32"                → 本檔 GPIO 全部有效
//   印出 "ESP32-S3"/"ESP32-C3"  → 本檔所有 GPIO 作廢，必須重配
#define BOARD_NAME       "ESP32 DevKit V1"          // [CONFIRMED] 使用者陳述
#define BOARD_CHIP_CHECK "ESP32"                    // Stage 1 banner 應印出這個字串
#define BOARD_SKU_NOTE   "ESP32 DevKit V1 (classic ESP32-WROOM-32, Type-C, CP2102)"  // [CONFIRMED] 2026-09-18 裝置管理員複核
#define BOARD_CANDIDATE  "esp32dev (Espressif ESP32 Dev Module)"    // platformio.ini 目前的 board 設定值
// 30-pin 與 38-pin 版本的腳位「名稱」通用，但實體排列不同。
// 接線一律照板上絲印文字找腳，不要數位置。
// USB 介面為 Type-C；橋接晶片為 CP2102（2026-09-18 由裝置管理員畫面確認）。

// ------------------------------------------------------------
//  2. Serial
// ------------------------------------------------------------
// 115200 是本專案的設定選擇，不是效能保證。
// platformio.ini 的 monitor_speed 必須與這個值一致。
#ifndef MONITOR_SPEED
#define MONITOR_SPEED 115200
#endif

#define HEARTBEAT_PERIOD_MS 500   // Step 1 心跳輸出間隔

// ------------------------------------------------------------
//  3. FSR402 ×2（Step 2 / Step 3）
// ------------------------------------------------------------
// GPIO34 / GPIO35 屬 ADC1，且為 input-only pin（沒有內部上下拉），
// 用在分壓感測剛好合適；ADC1 在未來加 Wi-Fi 時也不會被 Wi-Fi 佔用
// （ADC2 = GPIO0/2/4/12-15/25-27，Wi-Fi 啟用時不可讀）。
#define PIN_FSR1_SENSE 34   // ADC1_CH6  [CONFIRMED 設計選擇]
#define PIN_FSR2_SENSE 35   // ADC1_CH7  [CONFIRMED 設計選擇]

// 固定分壓電阻。使用者手上有 4.7k / 10k / 47k 各 10 顆。
// 10k = 起始值，在 0.2–2 N 這段變化最清楚。
//   47k → 對很輕的觸碰更靈敏，但較早飽和
//   4.7k → 要更大的力才飽和，適合分辨「用力抱」
// 先用 10k 取得真實曲線，再依實際受力與飽和情況調整。
#define FSR_FIXED_R_OHM 10000   // [CONFIRMED] 手上確定有這個阻值

// V_sense = 3.3V × R_fixed / (R_FSR + R_fixed)
// 按壓 → FSR 阻值下降 → 讀值上升。這是分壓關係，不是力學校準。
// ADC 設定。raw 讀值不等於力道；millivolt 是 API 校準後的估值，不是精密量測。
#define ADC_RESOLUTION_BITS 12          // 0..4095
#define ADC_ATTEN           ADC_11db    // 約可測到 ~3.1V，仍可能在強壓時飽和
#define FSR_SAMPLE_PERIOD_MS 20         // 50 Hz 取樣，保守起始值

// ------------------------------------------------------------
//  4. IMU — MPU6050（Step 4）
// ------------------------------------------------------------
// 使用者確認為 MPU6050（一般為 GY-521 breakout）。
// GY-521 板上有 3.3V 穩壓器，且 SDA/SCL 上拉電阻接在穩壓後的 3.3V，
// 所以 VCC 接 5V 時訊號仍為 3.3V，對 ESP32 安全，不需電平轉換。
// 來源：ProtoSupplies GY-521 產品頁。
// 若 VCC 接 VIN(5V) 掃不到，可改接 3V3 再試（社群常見做法，非規格保證）。
#define PIN_I2C_SDA 21   // [CONFIRMED 設計選擇] classic ESP32 慣例 SDA
#define PIN_I2C_SCL 22   // [CONFIRMED 設計選擇] classic ESP32 慣例 SCL
#define I2C_FREQ_HZ 100000   // 先用 100 kHz，接線與上拉驗證前不要衝 400k

#define IMU_CHIP        "MPU6050"   // [CONFIRMED] 使用者陳述，仍應以晶片絲印複核
#define IMU_I2C_ADDR    0x68        // AD0 浮接（模組內建 4.7k 下拉）= 0x68；AD0 接 3.3V = 0x69
// 流程仍然是：先跑 I2C scanner → 掃到 0x68 → 再選 library。
// 掃到位址只代表「有東西在回應」，不等於確認型號。
// XDA / XCL / AD0 / INT 四支不接。

// ------------------------------------------------------------
//  5. LCD 1.8" TFT（Step 5）
// ------------------------------------------------------------
// 2026-09-18：使用者目視確認背面排針為「8 腳小紅板」（A 型），
// 腳位名稱為 GND VCC SCL SDA RES DC CS BLK，下面接法對照以此為準。
// Controller 具體 IC 型號（ST7735 / ST7735S / ST7735R 哪個變體）仍未經
// IC 絲印逐一核對，維持 [CANDIDATE]，只影響 initR() 的 tab 參數，不影響接線。
#define LCD_CONTROLLER  "ST7735"    // [CANDIDATE] IC 型號未逐一核對，先用最常見的猜測
#define LCD_WIDTH       128         // [CONFIRMED] 隨 8 腳 A 型板一起確認
#define LCD_HEIGHT      160         // [CONFIRMED] 隨 8 腳 A 型板一起確認
// Adafruit_ST7735 的初始化變體：標準 1.8" 模組先用 INITR_BLACKTAB。
// 若顏色反了或邊緣有雜線，改試 INITR_GREENTAB / INITR_REDTAB（只改這一行，不用動接線）。

// 這片模組把 SPI 的 MOSI 印成 SDA、SCK 印成 SCL。
// 看到 SDA/SCL 不代表它是 I2C —— 接到 GPIO21/22 會亮背光但永遠空白。
#define PIN_LCD_SCK  18   // [CONFIRMED 設計選擇] VSPI CLK ← 模組印 SCL
#define PIN_LCD_MOSI 23   // [CONFIRMED 設計選擇] VSPI MOSI ← 模組印 SDA
#define PIN_LCD_CS   27   // [CONFIRMED 設計選擇]
#define PIN_LCD_DC   26   // [CONFIRMED 設計選擇] 模組印 DC
#define PIN_LCD_RST  25   // [CONFIRMED 設計選擇] 模組印 RES
// 邏輯 3.3V，與 ESP32 直接相容。VCC 接 3V3。
// 背光 BLK 接 3V3 常亮（沒有另外接 GPIO 控制亮度）；整片模組含背光約 50 mA（來源：Cirkit Designer）。
// 背光亮 ≠ controller 初始化成功。

#define LCD_UPDATE_PERIOD_MS 150   // Step 5：畫面更新跟 FSR 取樣分開排程，畫面慢不能拖慢取樣

// ------------------------------------------------------------
//  6. WiFi / 電腦通訊（Step 7 / Step 8）
// ------------------------------------------------------------
// ESP32-WROOM-32 內建 Wi-Fi，選用 SoftAP（ESP32 自己當熱點）而非連現有路由器：
// 黑客松現場網路不可控（client isolation / captive portal / 連線數限制），
// SoftAP 不依賴場館網路，IP 固定為 192.168.4.1，兩台裝置一對一，好排錯。
// [CONFIRMED 設計選擇]（2026-09-18 與使用者討論後決定）
#define WIFI_AP_SSID     "ESP32-Companion"
#define WIFI_AP_PASSWORD "12345678"   // WPA2 要求至少 8 碼，之後展示前可換

// Step 7：先用內建 WebServer.h 做最簡單的 HTTP hello world，
// 只證明「WiFi 硬體會動、電腦連得上」，不牽涉任何額外 library。
// Step 8：換成 WebSocket —— FSR 要持續回傳、LCD 要持續下發，
// 都是連續雙向的小封包，HTTP polling 效率差，WebSocket 更合適
// （握手一次後維持長連線，雙方都能主動推訊息）。
#define WS_PORT 81   // WebSocket port（Step 8），跟 HTTP 的 80 分開

// ------------------------------------------------------------
//  7. 功能開關 —— 失敗隔離用
// ------------------------------------------------------------
// 某個模組出問題時，把對應的開關關掉，就能回到上一個已通過的版本。
#define FEATURE_FSR       (APP_STAGE >= 2 && APP_STAGE <= 6)
#define FEATURE_IMU       (APP_STAGE == 4 || APP_STAGE == 6)
#define FEATURE_LCD       (APP_STAGE == 5 || APP_STAGE == 6)
#define FEATURE_WIFI_HTTP (APP_STAGE == 7)
#define FEATURE_WIFI_WS   (APP_STAGE == 8)

// ------------------------------------------------------------
//  8. 驗證層級標記 —— 寫文件時請誠實區分
// ------------------------------------------------------------
//   LEVEL_TABLE    接線表核對過
//   LEVEL_COMPILE  編譯成功
//   LEVEL_SIM      模擬成功
//   LEVEL_HW       實機成功  ← 只有這一層算數
