# 硬體清單 — 已確認 vs 待確認

更新日期：2026-09-15（使用者確認零件清單後修訂）
狀態欄意義：`CONFIRMED` = 使用者親口確認或有實機／datasheet 佐證；`CANDIDATE` = 推測；`UNKNOWN` = 完全沒資料

---

## 一、零件狀態表

| 零件 | 使用者陳述 | 目前判定 | 狀態 | 還缺什麼 |
|---|---|---|---|---|
| ESP32 開發板 | **ESP32 DevKit V1 ×1** | classic ESP32-WROOM-32 系列 | `CONFIRMED` | Stage 1 banner 的 `chip model` 複核；30-pin 還是 38-pin |
| USB 橋接晶片 | — | CP2102 或 CH340 | `UNKNOWN` | 板子背面絲印／裝置管理員那一行的名字 |
| LCD | **1.8 吋 TFT ×1** | 尺寸確認；controller 推測 ST7735（128×160） | `CANDIDATE` | 背面排針絲印（8 腳還是 13 腳）、IC 型號 |
| FSR402 | **×2** | Interlink FSR 402 兩腳可變電阻 | `CONFIRMED` | 確認是裸電阻片而非已焊轉接板 |
| 固定電阻 | **10kΩ ×10、4.7kΩ ×10、47kΩ ×10** | 分壓起始值採 10 kΩ | `CONFIRMED` | 用色環或電表把三種分開標示 |
| IMU 6DOF | **MPU6050 ×1** | 一般為 GY-521 breakout | `CONFIRMED` | 晶片絲印複核；確認是 GY-521 板型 |
| 麵包板 | 有 | — | `UNKNOWN` | 尺寸；電源軌中間是否斷開；ESP32 插入後兩側還剩幾孔 |
| 杜邦線 | 有 | — | `UNKNOWN` | 公公／公母／母母 各有幾條 |
| USB 資料線 | 未確認 | — | `UNKNOWN` | Stage 1 插上後裝置管理員有沒有新的 COM |

沒有確認擁有：萬用電表、烙鐵／焊錫、已焊好的排針、logic analyzer。
**不在庫存**（早期候選清單，不要當成有）：馬達、DRV8833、輪子、ToF 測距、TTP223、MAX98357A、K151。

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
| VCC | 5 V 標稱，板上有 3.3 V 穩壓器 |
| I2C 上拉 | 板上已有，接在**穩壓後的 3.3 V** → 對 3.3 V MCU 安全，不需電平轉換 |
| 位址 | AD0 浮接（內建 4.7 kΩ 下拉）= `0x68`；AD0 接 3.3 V = `0x69` |
| 上拉電阻阻值 | 來源未給 |

### 1.8" TFT LCD
| 項目 | 值 | 狀態 |
|---|---|---|
| 解析度 | 128 × 160 | `CANDIDATE` |
| Controller | ST7735（也有標 ST7735S / ST7735R） | `CANDIDATE` |
| 邏輯電壓 | 3.3 V | `CANDIDATE` |
| 背光 | 3.3–5 V；整片含背光約 50 mA | `CANDIDATE` |
| Library | `Adafruit ST7735 and ST7789` + `Adafruit GFX`，`initR(INITR_BLACKTAB)` | `CANDIDATE` |
| 是否有板載穩壓器／電平轉換／背光限流電阻 | **來源皆未說明** | `UNKNOWN` |

---

## 三、Stage 1 之後要填回來的欄位

跑完 `env:s1_serial`，把 banner 貼回來：

| 欄位 | 值 | 來源 |
|---|---|---|
| chip model | _待填_ | `ESP.getChipModel()`，應為 `ESP32` |
| chip revision | _待填_ | `ESP.getChipRevision()` |
| cores | _待填_ | `ESP.getChipCores()` |
| flash size | _待填_ | `ESP.getFlashChipSize()` |
| arduino-esp32 / IDF 版本 | _待填_ | `ESP.getSdkVersion()` |
| COM port | _待填_ | Windows 裝置管理員 |
| USB 橋接晶片 | _待填_ | 裝置管理員裝置名稱 |
| 排針數 | _待填_ | 一排 15 支 = 30 腳版；19 支 = 38 腳版 |

---

## 四、還需要的照片（剩三張）

1. **LCD 背面** — 排針絲印 + 板上 IC 型號（決定是 8 腳還是 13 腳板型、controller）
2. **MPU6050 正反面** — 晶片絲印複核 + 確認是 GY-521 板型
3. **ESP32 反面** — 看 USB 橋接晶片型號（決定驅動）

有商品連結的話，連結可以取代看不清的絲印。

---

## 五、這三張照片會改變什麼

| 照片內容 | 影響 |
|---|---|
| LCD 排針絲印 | 決定接線表用 A 型（8 腳）還是 B 型（13 腳）名稱對照 |
| LCD controller | 決定 library 與初始化變體（BLACKTAB / GREENTAB / REDTAB） |
| MPU6050 板型 | 確認上拉電阻接在穩壓後 3.3V 的前提是否成立 |
| USB 橋接晶片 | 決定要不要裝驅動、`upload_speed` 能開多快 |
