# 硬體清單 — 唯一權威版本

更新日期：2026-09-19（原本這份清單跟 Project 裡 `claude/CONFIRMED_HARDWARE_AND_WIRING.md` 的零件表分開維護、內容早就兜不起來——**從今天起這份才是唯一的零件清單**，那份文件的零件表已經拿掉，改成指到這裡；那份文件保留的是 GPIO 配置、接法細節、Stage 驗收結果，跟這裡的零件盤點是不同用途，不重複）。

狀態欄意義：`CONFIRMED` = 使用者親口確認或有實機／datasheet 佐證；`CANDIDATE` = 推測；`UNKNOWN` = 完全沒資料

---

## 一、零件狀態表

| 零件 | 使用者陳述 | 目前判定 | 狀態 | 還缺什麼 |
|---|---|---|---|---|
| ESP32 開發板 | **ESP32 DevKit V1 ×1** | classic ESP32-WROOM-32 系列，晶片為 ESP32-D0WD-V3（Stage 1 實機確認） | `CONFIRMED` | 30-pin 還是 38-pin 排針數仍未確認 |
| USB 橋接晶片 | — | **CP2102**（裝置管理員確認，見六節） | `CONFIRMED` | — |
| USB 接口型式 | — | **Type-C**（先前誤記為 Micro-USB） | `CONFIRMED` | — |
| USB 資料線 | 未確認 | Stage 1–5 多次 Build/Upload 都成功 | `CONFIRMED`（能傳資料） | — |
| LCD | **1.8 吋 TFT ×1** | 128×160；背面排針為 **8 腳小紅板（A 型）**，腳位 `GND VCC SCL SDA RES DC CS BLK`（使用者目視確認，2026-09-18）；controller 推測 ST7735 | 接法 `CONFIRMED`，IC 具體型號仍 `CANDIDATE` | IC 絲印逐一核對是 ST7735 / ST7735S / ST7735R 哪個變體（只影響 `initR()` 的 tab 參數，不影響接線） |
| FSR402 | **×2** | Interlink FSR 402 兩腳可變電阻 | `CONFIRMED` | 確認是裸電阻片而非已焊轉接板 |
| 固定電阻 | **10kΩ ×10、4.7kΩ ×10、47kΩ ×10** | 分壓起始值採 10 kΩ | `CONFIRMED` | — |
| IMU 6DOF | **MPU6050 ×1** | 一般為 GY-521 breakout | 零件 `CONFIRMED`，晶片身分 `CANDIDATE` | Stage 4（`s4_imu`）已能讀 `WHO_AM_I` 暫存器，實機讀到的值待回報；晶片絲印複核 |
| 無源蜂鳴器模組 MTARDALL112 | **×1** | Passive buzzer，需 PWM 訊號驅動才會發聲（不是通電就響） | `CONFIRMED`（零件＋接線，2026-09-19） | 已定案：GPIO32，掛在主板；測試程式 `s10_buzzer` 已寫好，待實機驗證回報 |
| ESP32-CAM（OV2640，內建 WiFi／藍牙）| **×1** | 獨立的第二顆 ESP32＋攝像頭模組，不是主控 DevKit V1 的周邊；**只接相機，不接其他任何零件**（使用者 2026-09-19 確認的限制） | `CONFIRMED`（零件＋接線＋測試程式，2026-09-19） | 已改為獨立 PlatformIO 專案 `esp32-cam-bringup/`（跟主板 `esp32-bringup/` 平行，不是同一個專案）；供電／燒錄／共用熱點接線見該專案 `docs/wiring_and_network.md`；待實機驗證回報 |
| INMP441 全向麥克風模組 | **×1** | I2S 數位麥克風 | `CONFIRMED`（零件＋接線，2026-09-19） | 已定案掛在**主板**（不掛 ESP32-CAM 板，因為 CAM 板只留給相機）；腳位 SCK=GPIO14／WS=GPIO13／SD=GPIO4；測試程式 `s11_mic` 已寫好，待實機驗證回報 |
| 麵包板 | 有 | — | `UNKNOWN` | 尺寸；電源軌中間是否斷開；ESP32 插入後兩側還剩幾孔 |
| 杜邦線 | 有 | — | `UNKNOWN` | 公公／公母／母母 各有幾條 |

沒有確認擁有：萬用電表、烙鐵／焊錫、已焊好的排針、logic analyzer。
**不在庫存**（早期候選清單，不要當成有）：馬達、DRV8833、輪子、ToF 測距、TTP223、MAX98357A、K151。

**新增的三項（蜂鳴器、ESP32-CAM、INMP441）狀態更新（2026-09-19）**：蜂鳴器與 INMP441 已完成 GPIO 配置＋測試程式（`s10_buzzer`、`s11_mic`，都在主板專案），待實機驗證回報；ESP32-CAM 已獨立成 `esp32-cam-bringup/` 專案並完成接線說明＋測試程式（`cam_stream` env），因為它是完全獨立的第二顆 ESP32、只接相機，走跟主板不同的燒錄流程（外接 USB-TTL、GPIO0 短接 GND 進燒錄模式），細節見該專案的 `docs/wiring_and_network.md`。三項共同的下一步都是「使用者實機測試回報結果」。

**網路拓樸也跟著改變**：兩塊 ESP32 並存後，電腦的 Wi-Fi 網卡沒辦法同時連「主板熱點」跟「CAM 板熱點」，改用共用熱點模式——主板與 CAM 板都改成 STA 加入同一個外部熱點（手機熱點或路由器），電腦也連同一個熱點。主板這端的開關是 `telemetry_local.h` 的 `TELEMETRY_USE_STA`（範本見 `include/telemetry_local.example.h`），CAM 板這端是 `esp32-cam-bringup/include/cam_wifi_local.h`（範本見同目錄的 `.example.h`）。詳細步驟見 `esp32-cam-bringup/docs/wiring_and_network.md` 第四節。

---

## 二、已可依 datasheet 填入的規格

### FSR402（Interlink FSR 402）
| 項目 | 值 |
|---|---|
| 感測區直徑 | 12.7 mm（整片外徑 18.28 mm） |
| 最小觸發力 | 0.1 N |
| 力量感測範圍 | 0.1 – 10.0 N |
| 未受力電阻 | > 10 MΩ |
| 反應時間 | < 3 µs |
| 重複性 | 同一片 ±2% / 片與片之間 ±6% |
| 遲滯 | +10% |
| 最大受力時電阻 | **datasheet 未給**，只有曲線圖 |

已知分歧：Adafruit 的教學寫力量範圍 0–100 N、電阻「輕壓 100 kΩ 到最大壓力 200 Ω」，
與 Interlink 的 0.1–10 N 對不起來。Adafruit 自己也指出該 datasheet 有數學上的不一致。
**結論：不要把 ADC 讀值換算成牛頓。**

### MPU6050 / GY-521
| 項目 | 值 |
|---|---|
| 腳位順序 | `VCC · GND · SCL · SDA · XDA · XCL · AD0 · INT` |
| VCC | 5 V 標稱，板上有 3.3 V 穩壓器（餵 3.3V 會沒有 dropout 餘裕，輸出反而不夠，見 Stage 4 討論） |
| I2C 上拉 | 板上已有，接在**穩壓後的 3.3 V** → 對 3.3 V MCU 安全，不需電平轉換 |
| 位址 | AD0 浮接（內建 4.7 kΩ 下拉）= `0x68`；AD0 接 3.3 V = `0x69` |
| WHO_AM_I 暫存器 | 位址 `0x75`，genuine 晶片應回 `0x68`；`s4_imu` 讀到後僅供參考，不擋資料顯示（clone 晶片可能不是 0x68 但功能正常） |

### 1.8" TFT LCD
| 項目 | 值 | 狀態 |
|---|---|---|
| 解析度 | 128 × 160 | `CONFIRMED`（隨 8 腳 A 型板一起確認） |
| 排針型式 | 8 腳小紅板（A 型），`GND VCC SCL SDA RES DC CS BLK` | `CONFIRMED`（2026-09-18 使用者目視確認） |
| Controller | ST7735（也有標 ST7735S / ST7735R），先用 `INITR_BLACKTAB` | `CANDIDATE` |
| 邏輯電壓 | 3.3 V | `CONFIRMED` |
| 背光 | 3.3V 常亮；整片含背光約 50 mA | `CANDIDATE`（來源：Cirkit Designer，未逐一核對這片實物） |
| Library | `Adafruit ST7735 and ST7789` + `Adafruit GFX` | `CONFIRMED`（已在 `s4_imu`／`s5_lcd` 實際使用） |

---

## 三、還需要的確認

1. **MPU6050 的 `WHO_AM_I` 讀值** —— `s4_imu` 開機畫面會印出來，回報這個值就能判斷是不是正牌晶片（不影響能不能用，只影響型號認定）。
2. **LCD controller IC 絲印** —— 決定 `initR()` 用 `BLACKTAB`／`GREENTAB`／`REDTAB`，不影響接線。
3. **蜂鳴器／INMP441 已完成腳位規劃與測試程式**（`s10_buzzer`／`s11_mic`），**ESP32-CAM 已獨立成專案**（`esp32-cam-bringup/`）並完成接線說明＋測試程式（`cam_stream`）；三者都還缺「使用者實機測試回報」這一步。
4. **麵包板尺寸、杜邦線庫存** —— 純粹清點用，不影響目前已經接好的部分。

---

## 四、Stage bring-up 進度對照

| Stage / env | 內容 | 狀態 |
|---|---|---|
| `s1_serial` | 最小 Serial 測試，晶片身分回報 | ✅ 實機驗證通過（2026-09-18） |
| `s2_fsr1` | 單一 FSR1 raw ADC | 程式已寫好，待你實機驗證回報 |
| `s3_fsr2` | 雙 FSR + Serial Plotter | 程式已寫好，待你實機驗證回報 |
| `s4_imu` | MPU6050 I2C scanner + 直接讀暫存器 + LCD 顯示 | 程式已寫好（2026-09-19 改版繞過 `WHO_AM_I` 擋關），待你實機驗證回報 |
| `s5_lcd` | LCD 顔文字表情（含眨眼）+ FSR1 讀值 | 程式已寫好，待你實機驗證回報 |
| `s6_all` | FSR + IMU + LCD 整合 telemetry | 未開始 |
| `s7_wifi_http` | WiFi SoftAP + HTTP hello world | 程式已寫好 |
| `s8_wifi_ws` | WiFi SoftAP + WebSocket | 程式已寫好 |
| `s9_wifi_sensors` | 真實 FSR + IMU telemetry，HTTP + WebSocket（取代 s6 的整合角色）| 程式已寫好；改共用熱點時設 `telemetry_local.h` 的 `TELEMETRY_USE_STA=1` |
| `s10_buzzer` | 無源蜂鳴器 MTARDALL112 PWM 測試（主板） | 程式已寫好（2026-09-19），待你實機驗證回報 |
| `s11_mic` | INMP441 I2S 麥克風測試（主板） | 程式已寫好（2026-09-19），待你實機驗證回報 |
| `s12_mic_wav` | INMP441 錄音，原始 PCM 經 Serial（921600 baud）倒到電腦，用 `tools/record_mic_wav.py` 存成 .wav 播放 | 程式已寫好（2026-09-19），待你實機驗證回報 |
| `esp32-cam-bringup/cam_stream` | ESP32-CAM 相機 MJPEG 串流（獨立專案，獨立板子，見專案內 `docs/wiring_and_network.md`）| 程式已寫好（2026-09-19），待你實機驗證回報 |

Stage 1 實機回報的晶片身分：`chip model = ESP32-D0WD-V3`、`chip revision = 3`、`cores = 2`、`cpu freq = 240 MHz`、`flash size = 4,194,304 bytes`、`arduino-esp32 SDK = v4.4.7-dirty`、`efuse MAC = 98B091DF948C`。

---

## 五、還需要的照片

1. **MPU6050 正反面** —— 晶片絲印複核，確認是不是正牌 GY-521 板型（功能已可用，這項只影響型號認定）
2. **LCD 正面 IC 絲印** —— 決定 `initR()` 的 tab 參數

有商品連結的話，連結可以取代看不清的絲印。
