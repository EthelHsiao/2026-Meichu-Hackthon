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
// 2026-09-19：10k 起始值實測太不靈敏（要壓很大力才有反應，變化幅度也小）——
// 原因是 10k 遠小於 FSR 輕壓時的電阻（幾十~上百 kΩ），分壓結果被 10k 鉗制在
// 低檔，FSR 電阻怎麼變、輸出電壓都變化很小。換成 47k 後使用者實測確認變好：
// 47k 跟 FSR 輕壓時的電阻量級接近，同樣的施力變化能換算成明顯得多的電壓/ADC
// 讀值變化。代價是大力按壓那端會更早貼近 3.3V 飽和，犧牲高力道範圍的解析度
// 換取輕~中力道的靈敏度——FSR1、FSR2 兩顆都要一起換，才會兩邊行為一致。
#define FSR_FIXED_R_OHM 47000   // [CONFIRMED] 2026-09-19 使用者實測換成 47k 後確認變靈敏

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

// 2026-09-19 實機發現：I2C scan 掃得到 0x68，但 Adafruit_MPU6050::begin()
// 初始化失敗。加了 WHO_AM_I（暫存器 0x75）診斷後，讀到的值是 0x74——
// 跟已知的 MPU6050(0x68)、MPU6500(0x70)、MPU9250(0x71)、MPU9255(0x73)
// 都對不上，型號目前無法確認，先當「未知的 Invensense 相容晶片」處理，
// 不要再假設它是標準 MPU6050。
// 因為 register map（0x6B PWR_MGMT_1 / 0x1B GYRO_CONFIG / 0x1C ACCEL_CONFIG /
// 0x3B 起 14 byte 原始輸出）在這個系列幾乎共用，s4_imu 跟 s9_wifi_sensors
// 都已經改成：begin() 失敗時，直接操作暫存器喚醒＋設定量測範圍＋讀原始值，
// 繞過 Adafruit 驅動的型號比對。量測範圍固定 ±8g / ±500dps，換算比例是
// [CANDIDATE]，還沒拿真實角度/靜置重力對過準確度。

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

// 2026-09-19 補充：加入 ESP32-CAM 板之後，電腦的 Wi-Fi 網卡不能同時連兩個
// ESP32 各自開的熱點（實體限制，不是效能問題）。這種情況改用「共用熱點」
// 模式——主板跟 ESP32-CAM 都改成 STA，一起加入同一個外部熱點（手機熱點或
// 路由器），電腦也連同一個熱點，三方就在同一個區網互通。
// 開關已經做在 telemetry_config.h：複製 telemetry_local.example.h 成
// telemetry_local.h，設 TELEMETRY_USE_STA 1、填入熱點帳密即可，不用改這裡。
// 沒開這個開關時，行為維持原本的 SoftAP（此區塊上面說明的模式）。

// Step 7：先用內建 WebServer.h 做最簡單的 HTTP hello world，
// 只證明「WiFi 硬體會動、電腦連得上」，不牽涉任何額外 library。
// Step 8：換成 WebSocket —— FSR 要持續回傳、LCD 要持續下發，
// 都是連續雙向的小封包，HTTP polling 效率差，WebSocket 更合適
// （握手一次後維持長連線，雙方都能主動推訊息）。
#define WS_PORT 81   // WebSocket port（Step 8），跟 HTTP 的 80 分開

// ------------------------------------------------------------
//  7. 無源蜂鳴器 MTARDALL112（Step 10）
// ------------------------------------------------------------
// 無源（passive）蜂鳴器本身不含振盪電路，通電只會有「喀」一聲，
// 必須由 MCU 不斷送方波（PWM）才會連續發聲，音高由 PWM 頻率決定；
// 這跟有源（active）蜂鳴器不同——有源的接電就響、頻率固定不可調。
// 2026-09-19 使用者確認：手上這片 MTARDALL112 是 3 腳「驅動模組」
// （VCC / I-O(S) / GND，板上有小顆驅動電晶體），不是裸 2 腳蜂鳴器元件，
// 所以除了訊號腳，VCC 也要接電源，不能只接訊號腳跟 GND 兩條線。
// 選腳理由：GPIO32 空腳、非 strapping、非 flash 腳，純數位 PWM 輸出，
// 跟現有 FSR(34/35)、I2C(21/22)、SPI(18/23/25/26/27) 都不衝突。
#define PIN_BUZZER 32   // [CONFIRMED 設計選擇] 接模組的 I-O（也常標 S）腳
// 模組 VCC 接 3V3，GND 接 GND；這兩條不接的話訊號腳送 PWM 也不會有聲音。

// ------------------------------------------------------------
//  8. INMP441 全向麥克風（I2S，Step 11）
// ------------------------------------------------------------
// INMP441 是 I2S 數位麥克風，不是類比、也不是 I2C——三條線
// （SCK 位元時脈、WS 左右聲道選擇、SD 資料輸出）在 classic ESP32 上
// 可接任意 GPIO（I2S 走內部訊號矩陣，不像 SPI/I2C 有固定硬體腳位）。
// 選腳理由：GPIO14/13/4 皆空腳、非 strapping、非 flash 腳，且刻意避開
// GPIO16/17（部分模組上這兩腳留給 PSRAM；這片 WROOM-32 沒有 PSRAM 用不到，
// 但避開它們讓接線在不同 ESP32 板子上都通用）。
// 決定：這顆麥克風掛在主板，不是 ESP32-CAM 板——因為 ESP32-CAM 板已確定
// 「不能再接其他東西」，只留給相機用。
// L/R 選擇：模組上的 L/R 腳位接 GND，輸出左聲道（單聲道麥克風固定這樣接）。
#define PIN_MIC_SCK 14   // [CONFIRMED 設計選擇] I2S bit clock（模組印 SCK）
#define PIN_MIC_WS  13   // [CONFIRMED 設計選擇] I2S word select（模組印 WS 或 LRCL）
#define PIN_MIC_SD  4    // [CONFIRMED 設計選擇] I2S data out（模組印 SD 或 DOUT）
#define MIC_SAMPLE_RATE_HZ 16000    // 16kHz 對語音/環境音偵測夠用，不追求音樂音質
#define MIC_I2S_PORT I2S_NUM_0

// 2026-09-19 實機發現的重要限制：classic ESP32（不是 S3）的 I2S RX 週邊，
// 設成 I2S_CHANNEL_FMT_ONLY_LEFT / ONLY_RIGHT 單聲道模式時讀回來的資料
// 整片是 0——這是硬體/驅動限制，接線完全正確也一樣。s11_mic／s12_mic_wav
// 已經改成用立體聲 I2S_CHANNEL_FMT_RIGHT_LEFT，再只取聲道 0（buffer 裡
// i*2 那個位置，L/R 腳接 GND 時實測資料就在這裡）。之後任何新程式碼只要
// 用到這顆麥克風，都要照這個模式接，不要用 ONLY_LEFT。

// Step 12：把錄到的聲音實際倒出來存成 .wav 聽，需要比平常快很多的 Serial 鮑率。
// 16kHz、16-bit、單聲道 = 32,000 bytes/秒；115200 baud 只有約 11,520 bytes/秒，
// 塞不下會漏資料、聲音失真變速。921600 是這個專案上傳韌體本來就在用、
// 已經驗證過這片 CP2102 撐得住的速度，這裡直接沿用。
#define MIC_WAV_STREAM_BAUD 921600

// ------------------------------------------------------------
//  9. 功能開關 —— 失敗隔離用
// ------------------------------------------------------------
// 某個模組出問題時，把對應的開關關掉，就能回到上一個已通過的版本。
#define FEATURE_FSR       (APP_STAGE >= 2 && APP_STAGE <= 6)
#define FEATURE_IMU       (APP_STAGE == 4 || APP_STAGE == 6)
#define FEATURE_LCD       (APP_STAGE == 5 || APP_STAGE == 6)
#define FEATURE_WIFI_HTTP (APP_STAGE == 7)
#define FEATURE_WIFI_WS   (APP_STAGE == 8)
#define FEATURE_BUZZER    (APP_STAGE == 10)
#define FEATURE_MIC       (APP_STAGE == 11 || APP_STAGE == 12)

// ------------------------------------------------------------
//  10. 驗證層級標記 —— 寫文件時請誠實區分
// ------------------------------------------------------------
//   LEVEL_TABLE    接線表核對過
//   LEVEL_COMPILE  編譯成功
//   LEVEL_SIM      模擬成功
//   LEVEL_HW       實機成功  ← 只有這一層算數
