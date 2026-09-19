# 分階段接線表

**設定版本來源**：`include/board_config.h`
此文件與該檔案必須一致；改任何一邊都要同步另一邊。

**互動教學版**：完整的零基礎解說、互動麵包板、色環計算器與分壓試算器，
見 Artifact「ESP32 接線工作台」。這份 md 是給終端機旁邊快速核對用的精簡版。

> 動任何一條線之前先**拔掉 USB**。不要同時用外部電源與 USB 供電。
> 不要把 GPIO 當供電腳。

已確認零件：ESP32 DevKit V1 ×1、FSR402 ×2、MPU6050 ×1、1.8" TFT LCD ×1、
電阻 10kΩ ×10 / 4.7kΩ ×10 / 47kΩ ×10。

---

## 建議線色（全程沿用）

| 線色 | 代表 |
|---|---|
| 紅 | 3.3 V |
| 橘 | 5 V（VIN） |
| 黑 | GND |
| 黃 | FSR 類比訊號 |
| 藍 | I2C SDA |
| 綠 | I2C SCL |
| 紫 | SPI SCK / MOSI |
| 白 / 棕 / 粉 | LCD CS / DC / RST |

---

## Step 1 — 只接 USB

| Net | 連接 |
|---|---|
| — | ESP32 ←USB 資料線→ 電腦 |

麵包板上什麼都不插。FSR、IMU、LCD 全部放旁邊。

**理由**：任何後續問題都要能區分是「板子/工具鏈」還是「外接模組」。
Step 1 通過之後，它就是你永遠可以退回去的已知良好狀態。

**驗收**：裝置管理員出現 COM 埠；Serial Monitor 持續收到變動數字；
按 EN 重置後恢復；banner 的 chip model 印出 `ESP32`。

---

## Step 2 — 加入 FSR 1

FSR402 是**兩腳的可變電阻**，沒有獨立的 OUT 腳，也**不分正負**。
所謂的 OUT 是你自己用一顆固定電阻做出來的分壓中點。

```
   3.3V ───┬─────────────┐
           │            [FSR1]
           │             │
           │             ├──────────► GPIO34 (ADC1_CH6)   ← 這是 SENSE 節點
           │             │
           │          [10 kΩ]
           │             │
   GND  ───┴─────────────┘
```

| Net | 連接 |
|---|---|
| `FSR_SUPPLY` | ESP32 `3V3` → 麵包板 ＋ 軌 → FSR1 任一腳 |
| `FSR1_SENSE` | FSR1 另一腳 ＋ R1(10kΩ) 一腳 ＋ `GPIO34` — **三者同一個電氣節點（同一條 5 孔）** |
| `GND` | R1 另一腳 → 麵包板 － 軌 → ESP32 `GND` |

分壓關係：`V_sense = 3.3V × R_fixed / (R_FSR + R_fixed)`
按壓 → FSR 阻值下降 → **讀值上升**。這是分壓關係，**不是把 ADC 值換算成牛頓的力學校準**。

| 項目 | 值 | 狀態 |
|---|---|---|
| R_fixed | 10 kΩ | `CONFIRMED` 手上有；47k 對輕觸更靈敏、4.7k 較晚飽和 |
| ADC 解析度 | 12-bit（0–4095） | 程式設定 |
| ADC 衰減 | `ADC_11db` | 程式設定，強壓時仍可能飽和 |

> 不要照抄 Adafruit 的 Arduino Uno 5V 範例。那是 5V 分壓，
> 接到 ESP32 的 ADC 腳會超過 3.3V 上限。這裡一律用 3.3V。

**驗收**：raw ADC 按壓／放開有可重複變化。記錄未按壓基線、正常按壓、飽和值。

**FSR 接腳很細**，插麵包板容易接觸不良。判斷方法：不碰感測區、只輕動排線，
若讀值大幅跳動就是接觸問題，不是量到力。

---

## Step 3 — 加入 FSR 2

複製一組**完全獨立**的分壓：另一顆固定電阻、另一個 SENSE 節點、另一個 ADC 腳。

| Net | 連接 |
|---|---|
| `FSR_SUPPLY` | 與 FSR1 **共用** ＋ 軌 |
| `FSR2_SENSE` | FSR2 ＋ R2(10kΩ) ＋ `GPIO35` (ADC1_CH7) |
| `GND` | 與 FSR1 **共用** － 軌 |

**共用 3V3 與 GND，但絕對不共用 SENSE 節點。**
若兩條曲線永遠同步變化 → 多半是 SENSE 誤接在一起，或程式讀到同一支腳。

**驗收**：Serial Plotter 兩條曲線；只按一片時對應曲線主要改變。
這階段只畫兩路 FSR，不要混入時間戳或尺度差很多的 IMU 值。

---

## Step 4 — MPU6050（GY-521）

| Net | 模組腳 | ESP32 | 線色 |
|---|---|---|---|
| `VCC` | `VCC` | `VIN`（5V） | 橘 |
| `GND` | `GND` | `GND` | 黑 |
| `SDA` | `SDA` | `GPIO21` | 藍 |
| `SCL` | `SCL` | `GPIO22` | 綠 |

`XDA` `XCL` `AD0` `INT` 四支**不接**。

- GY-521 板上**已有 I2C 上拉電阻，接在模組穩壓後的 3.3V**，
  所以 VCC 接 5V 時 SDA/SCL 仍為 3.3V，對 ESP32 安全，不需電平轉換。
  （來源：ProtoSupplies GY-521 產品頁）
- `AD0` 模組內建 4.7kΩ 下拉，浮接 = 位址 `0x68`；接 3.3V = `0x69`。
- 若 VCC 接 5V 掃不到，拔電後改接 `3V3` 再試一次。

**流程**：先跑 I2C scanner → 掃到 `0x68` → 再查晶片／選 library。
掃到位址只表示有回應，**不足以認定型號**。不要預設就用某個 library 的預設值。

**驗收**：`ax ay az gx gy gz` 持續輸出；平放靜止時加速度**仍含重力**（不要求歸零）；
gyro 可能有偏移；傾斜與旋轉時對應軸有合理變化。標明單位（g 或 m/s²、deg/s 或 rad/s）。

---

## Step 5 — LCD 1.8" TFT

**接之前先翻到背面，把那排絲印一字不漏抄下來**，照你板子上的名稱對，不要照本表的名稱對。

常見兩種板型：
- **A 型 8 腳小紅板**：`GND · VCC · SCL · SDA · RES · DC · CS · BLK`
- **B 型 13 腳（常帶 SD 卡槽）**：`VIN · GND · RST · CS · D/C · MOSI · MISO · SCK · LED+ · LED-`

以 A 型為例：

| 模組腳 | 它其實是 | ESP32 | 線色 |
|---|---|---|---|
| `VCC` | 供電 3.3V | `3V3` | 紅 |
| `GND` | 地 | `GND` | 黑 |
| `SCL` | **SPI SCK，不是 I2C** | `GPIO18` | 紫 |
| `SDA` | **SPI MOSI，不是 I2C** | `GPIO23` | 紫 |
| `RES` | Reset | `GPIO25` | 粉 |
| `DC`（或 `A0`/`RS`） | Data/Command | `GPIO26` | 棕 |
| `CS` | Chip Select | `GPIO27` | 白 |
| `BLK`（或 `LED`） | 背光 | `3V3` | 紅 |

- 邏輯 3.3V，與 ESP32 直接相容。
- controller 通常是 ST7735；library 用 `Adafruit ST7735 and ST7789` + `Adafruit GFX`，
  初始化 `tft.initR(INITR_BLACKTAB)`。顏色反了或邊緣有雜線 → 改 `GREENTAB` / `REDTAB`。
- 整片含背光約 50 mA。**背光亮 ≠ controller 初始化成功。**

**驗收順序（不要跳）**：背光亮 → 整片純色 → 文字且方向正確 → 最後才顯示 FSR 讀值。
LCD 更新與感測取樣分開排程；關掉 LCD 功能要能回到 Step 3 的已通過版本。

---

## 全部接完 — 18 條線

| # | 線色 | 從 | 到 |
|---|---|---|---|
| 1 | 紅 | ESP32 `3V3` | 麵包板 ＋ 軌 |
| 2 | 黑 | ESP32 `GND` | 麵包板 － 軌 |
| 3 | 紅 | ＋ 軌 | FSR1 腳 A |
| 4 | — | FSR1 腳 B ＋ R1(10k) | SENSE1 排 |
| 5 | 黑 | R1 另一腳 | － 軌 |
| 6 | 黃 | SENSE1 排 | `GPIO34` |
| 7 | 紅 | ＋ 軌 | FSR2 腳 A |
| 8 | — | FSR2 腳 B ＋ R2(10k) | SENSE2 排 |
| 9 | 黑 | R2 另一腳 | － 軌 |
| 10 | 黃 | SENSE2 排 | `GPIO35` |
| 11 | 橘 | ESP32 `VIN` | MPU6050 `VCC` |
| 12 | 黑 | － 軌 | MPU6050 `GND` |
| 13 | 藍 | `GPIO21` | MPU6050 `SDA` |
| 14 | 綠 | `GPIO22` | MPU6050 `SCL` |
| 15 | 紅 | ＋ 軌 | LCD `VCC` ＋ `BLK` |
| 16 | 黑 | － 軌 | LCD `GND` |
| 17 | 紫 ×2 | `GPIO18` / `GPIO23` | LCD `SCL` / `SDA` |
| 18 | 白/棕/粉 | `GPIO27`/`GPIO26`/`GPIO25` | LCD `CS`/`DC`/`RES` |

---

## 電源注意事項（全階段適用）

- bring-up 階段只用 **USB 單一供電來源**。
- 把 `3V3` 與 `GND` 各拉一條到麵包板電源軌。
- 很多麵包板的電源軌**中間是斷的**，需要跨接短線才會全長導通。
  用視覺檢查那一排有沒有斷口，不要因為紅線／藍線的顏色就假定所有孔相通。
- DevKit V1 板寬約 23.4 mm，麵包板孔距 2.54 mm、A–J 跨距約 27.9 mm，
  推算插上後兩側各只剩約一排孔（估算值，請實際插上去數）。
  空間不夠就把板子插在最邊緣，或改用母對公杜邦線不插麵包板。
- 不要同時用外部電源與 USB 反向供電，也不要把 GPIO 當供電腳。

---

## 腳位選擇的理由

| 腳位 | 用途 | 為什麼 |
|---|---|---|
| `GPIO34` `GPIO35` | FSR1 / FSR2 | ADC1（Wi-Fi 開著也能讀）；input-only，剛好只需要輸入 |
| `GPIO21` `GPIO22` | I2C SDA / SCL | classic ESP32 慣例腳，library 預設 |
| `GPIO18` `GPIO23` | SPI SCK / MOSI | VSPI 硬體預設腳 |
| `GPIO27` `GPIO26` `GPIO25` | LCD CS / DC / RST | 三支都不是 strapping pin，也不是 flash 腳 |

避開的腳：`GPIO6–11`（接 flash）、`GPIO0/2/5/12/15`（strapping，開機敏感）、
`GPIO1/3`（TX0/RX0，USB 序列埠用）。

---

## 接線圖

互動版見 Artifact「ESP32 接線工作台」（含互動麵包板節點圖與分壓試算器）。
逐孔精確的 `docs/wiring.svg` 待實機照片回來後再畫；未確認的腳位會標 TBD，
不畫看似精確但其實虛構的孔位。
