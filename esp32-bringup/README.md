# ESP32 陪伴裝置 — 硬體 bring-up

> **2026-09-19：Wi-Fi 感測器測試已新增**：使用 `s9_wifi_sensors` 同時讀取 FSR ×2 / MPU6050，
> 提供 HTTP API、WebSocket 即時串流、瀏覽器測試頁與電腦 JSONL 記錄工具。
> 從 [Step 9 操作與 API 規格](docs/telemetry.md) 開始。已通過編譯與本機模擬，實機待驗收。

工具鏈：**Windows + VS Code + PlatformIO IDE extension**（不需要安裝 Arduino IDE）

目前通過到：**Step 1（實機驗證通過，2026-09-18）**
下一步：**Step 7 — WiFi SoftAP + HTTP hello world**

> 2026-09-18 更新：USB 驅動已確認並裝好——橋接晶片是 **CP2102**，接口是 **Type-C**。
> Step 1（`s1_serial`）已經 Build → Upload → Monitor 全部成功，chip model 回報
> `ESP32-D0WD-V3`（classic ESP32 家族，不是 S3/C3/C6），代表 `board_config.h`
> 的 GPIO 配置前提成立，不需要重配。Heartbeat 持續遞增、重開機後 banner 重印
> 都驗證過；Serial Monitor 打字 echo 測試還沒做，建議之後補做一次。
> 接下來請把 env 切成 `s7_wifi_http`，重複同一套 Build → Upload → Monitor 流程。

> 誠實標註：這個 repo 裡的所有 GPIO 與板型都還是**候選值**。
> 沒有任何一項經過你的實機驗證。Stage 1 跑完後才會有第一筆真實證據。

---

## 一、一次性環境安裝（約 10 分鐘，大多是自動下載）

### 1. 裝 PlatformIO IDE extension

VS Code → 左側 Extensions（`Ctrl+Shift+X`）→ 搜尋 **PlatformIO IDE** → Install。

裝完它會自己在背景下載 PlatformIO Core，右下角會有進度。**等它跑完再繼續**，
第一次可能要 3–5 分鐘。完成後 VS Code 左側會多一個外星人頭圖示。

### 2. 用 VS Code 開這個資料夾

`File → Open Folder…` → 選 `C:\Users\USER\Ethel\NYCU\2026_Meichu\esp32-bringup`

**要開到 `esp32-bringup` 這一層**（也就是有 `platformio.ini` 的那一層），
開錯層 PlatformIO 不會認得這是專案。

開啟後 PlatformIO 會自動下載 `espressif32` platform 與 ESP32 toolchain，
同樣要等（第一次約 200–400 MB）。底下狀態列出現 PlatformIO 的圖示列就算好了。

### 3. USB 驅動（可能不用裝）

先**不要**急著裝驅動。做完下面的 Step 1-A 再決定。

---

## 二、Step 1：最小 Serial 測試

### Step 1-A　先確認電腦看得到板子

1. **只接 ESP32**，不要接 FSR / IMU / LCD。麵包板上什麼都不要插。
2. 用 USB 線接電腦。⚠ 有些 USB 線只有充電線芯、沒有資料線芯，
   那種線插上去 Windows 完全沒反應。
3. `Win+X` → **裝置管理員**（Device Manager）→ 展開 **連接埠 (COM 和 LPT)**。
4. **拔掉 USB、再插上**，看哪一個 COM 項目消失又出現 — 那個就是你的板子。

記下兩件事：

- COM 編號（例如 `COM5`）
- 它的名字。常見兩種：
  - `Silicon Labs CP210x USB to UART Bridge` → CP2102 晶片
  - `USB-SERIAL CH340` → CH340 晶片

**如果「連接埠」底下什麼都沒出現**，或出現黃色驚嘆號的未知裝置：

| 情況 | 處理 |
|---|---|
| 完全沒反應（連未知裝置都沒有） | 換一條**確定能傳資料**的 USB 線，再換一個 USB 孔 |
| 出現黃色驚嘆號 / 未知裝置 | 缺驅動。看板子上 USB 接頭旁那顆小 IC 的絲印：<br>`CP2102` → 裝 Silicon Labs CP210x VCP driver<br>`CH340`/`CH9102` → 裝 WCH CH341SER driver |

> 這一步請把裝置管理員那一行的**名字**告訴我，我會寫進 `docs/hardware_inventory.md`。

### Step 1-B　編譯

VS Code 底部狀態列有一排小圖示，或用左側外星人圖示 → `PROJECT TASKS`。

1. 狀態列最左邊會顯示目前 env，應該是 **`env:s1_serial`**。
   如果不是，點它，選 `s1_serial`。
2. 按狀態列的 **✓（Build）**，或 `Ctrl+Alt+B`。

預期：終端機最後出現

```
========================= [SUCCESS] Took xx.xx seconds =========================
```

RAM / Flash 使用率會印出來，Flash 大約 20 萬 bytes 上下。

> 如果 Build 失敗且錯誤訊息提到 `esp32dev` 或 platform 下載失敗，
> 多半是第一次下載沒跑完。等網路下載完再按一次。

### Step 1-C　上傳

1. 按狀態列的 **→（Upload）**，或 `Ctrl+Alt+U`。
2. 終端機會出現 `Connecting........___`

**如果一直停在 `Connecting....` 然後失敗**：
在它印 `Connecting` 的時候，**按住板子上的 `BOOT` 鍵**（有些板印 `IO0`），
按住約 2 秒再放開。有些 38-pin 板的自動下載電路不完整，需要手動進 bootloader。

成功會看到：

```
Writing at 0x00010000... (100 %)
Wrote xxxxx bytes ...
Hash of data verified.
Leaving...
Hard resetting via RTS pin...
```

### Step 1-D　看輸出

按狀態列的 **插頭圖示（Serial Monitor）**，或 `Ctrl+Alt+S`。

> ⚠ **一個 COM port 同時只能被一個程式占用。**
> 如果 Upload 報 `could not open port ... Access is denied`，
> 是 Serial Monitor 還開著。先在終端機按 `Ctrl+C` 關掉它再 Upload。

---

## 三、Step 1 驗收條件

打開 Serial Monitor 後，按一下板子上的 **EN / RST** 鍵（讓它重開機），你應該看到：

```
============================================================
 ESP32 bring-up / Stage 1 : minimal serial
============================================================
 賣場料號(使用者提供) : XO148-1 / 38-pin ESP32 module
 platformio board 候選 : ESP32-WROOM-32 DevKit (38-pin) [UNCONFIRMED]
------------------------------------------------------------
 以下由晶片自己回報，這才是板型的實際證據：
   chip model     : ESP32
   chip revision  : 3
   cores          : 2
   cpu freq       : 240 MHz
   flash size     : 4194304 bytes
   ...
   reset reason   : EXT (外部reset腳)
------------------------------------------------------------
...
============================================================

HB seq=1 t_ms=1703 uptime_s=1.7 heap=298765
HB seq=2 t_ms=2203 uptime_s=2.2 heap=298765
HB seq=3 t_ms=2703 uptime_s=2.7 heap=298765
```

**三項都要成立才算通過：**

| # | 驗收動作 | 應該看到 |
|---|---|---|
| 1 | 什麼都不做，看 30 秒 | `HB seq=` 每 0.5 秒 +1，`t_ms` 一直變大，不會卡住 |
| 2 | 按板子上的 **EN / RST** 鍵 | banner 重印一次，`seq` 從 1 重新開始 |
| 3 | 在 Serial Monitor 打幾個字按 Enter | 出現 `[echo] 0x41 'A'` 之類的回應 |

第 3 項是確認你讀的真的是這塊板子，不是某個藍牙虛擬 COM port。

### ⭐ 請回報給我的東西

把 banner 那一整段（從 `chip model` 到 `reset reason`）複製貼給我。
`chip model` 那一行決定了後面所有 GPIO 配置：

- 印出 `ESP32` → `board_config.h` 的候選腳位成立，可以往 Step 2 走
- 印出 `ESP32-S3` / `ESP32-C3` / 其他 → 那些 GPIO 全部作廢，我重配一份

---

## 四、卡住的話先查這幾項

| 症狀 | 依序檢查 |
|---|---|
| 裝置管理員沒有新的 COM | ① USB 線是不是只充電 ② 換 USB 孔 ③ 依橋接晶片裝驅動 |
| Upload 卡在 `Connecting....` | ① 按住 BOOT 鍵再上傳 ② Serial Monitor 沒關掉 ③ `upload_speed` 降成 `115200` |
| Monitor 全是亂碼 `���` | baud 不符。`platformio.ini` 的 `monitor_speed` 與程式的 `MONITOR_SPEED` 都必須是 115200 |
| Monitor 一片空白 | ① 按 EN/RST 讓它重印 banner ② 確認 Monitor 開在正確的 COM port |
| 一直重複開機 / 印 `BROWNOUT` | 供電不足或短路。這階段還沒接東西就不該發生；若發生請換 USB 孔或換線 |
| `Access is denied` / port busy | 有另一個程式占著 COM。關掉 Serial Monitor、Arduino IDE、其他終端機 |

完整的症狀對照表在 `docs/debug.md`。

---

## 五、專案結構

```
esp32-bringup/
├── platformio.ini          每個 env = 交接文件的一個階段
├── include/
│   └── board_config.h      ★ 所有 GPIO / 參數的單一事實來源
├── src/
│   └── main.cpp            用 APP_STAGE 切換階段
├── docs/
│   ├── hardware_inventory.md   已確認 vs 待確認的零件
│   ├── wiring.md               分階段接線表
│   └── debug.md                症狀 → 排查
└── logs/                   實機 CSV 會放這裡（sample/mock 分開標示）
```

各 env 對應：

| env | 階段 | 狀態 |
|---|---|---|
| `s1_serial` | Step 1 最小 Serial | ✅ 已寫好，待你實機驗收 |
| `s2_fsr1`   | Step 2 單 FSR 分壓 | ⏸ 空殼，等固定電阻阻值 |
| `s3_fsr2`   | Step 3 雙 FSR 曲線 | ⏸ 空殼 |
| `s4_imu`    | Step 4 I2C scanner / IMU | ⏸ 空殼，等 IMU 型號 |
| `s5_lcd`    | Step 5 LCD | ⏸ 空殼，等 controller 型號 |
| `s6_all`    | Step 6 整合 telemetry | ⏸ 空殼 |
| `s7_wifi_http` | Step 7 WiFi SoftAP + HTTP hello world | ✅ 已寫好，待實機驗收 |
| `s8_wifi_ws`   | Step 8 WiFi SoftAP + WebSocket（FSR/LCD 實際要用的通道） | ✅ 已寫好，待實機驗收 |

> Step 2 之後才會需要看曲線。PlatformIO 沒有內建 Serial Plotter，
> 屆時我會加 **Teleplot** extension 的輸出格式（`>fsr1:1234`），
> 在 VS Code 裡就能畫圖，不用切到 Arduino IDE。這一步等 Step 1 通過再處理。

---

## 六、Step 7 / Step 8：電腦 ↔ ESP32 的 WiFi 通訊

跟 Step 2–6（FSR / IMU / LCD）是不同的軸線，不互相依賴，但建議還是先把
**Step 1 在實機上跑過、驗收條件全部打勾**之後再碰這兩步——原因是 Step 7/8
沿用同一份 `MONITOR_SPEED` / Serial 基礎設施，先確認那條路徑穩定，
WiFi 出問題時才不會搞不清楚是哪一層的鍋。

- **Step 7（`s7_wifi_http`）**：ESP32 用內建 `WiFi.softAP()` 自己開一個 WiFi
  熱點（SSID `ESP32-Companion`，密碼 `12345678`，IP 固定 `192.168.4.1`），
  跑一個最陽春的 HTTP server。驗收：電腦連上這個熱點後，
  終端機打 `curl http://192.168.4.1/`，看到 `Hello from ESP32`。
- **Step 8（`s8_wifi_ws`）**：換成 WebSocket（library：`links2004/WebSockets`，
  已寫進 `platformio.ini` 的 `lib_deps`，PlatformIO 會自動下載，第一次編譯會
  比較久）。ESP32 每秒主動推一則心跳訊息。電腦端測試（`pip install
  websockets` 之後）：

  ```python
  import asyncio, websockets

  async def main():
      async with websockets.connect("ws://192.168.4.1:81/") as ws:
          while True:
              print(await ws.recv())

  asyncio.run(main())
  ```

  持續印出 `{"hb": ...}` 就算 Step 8 過關。之後把 Stage 8 `loop()` 裡的假心跳
  換成 `analogRead(PIN_FSR1_SENSE)` / `PIN_FSR2_SENSE`（Step 3 驗證過的真實
  讀值），就是實際會用在陪伴裝置上的通道。

選 SoftAP 而不是連現有路由器，是因為黑客松現場網路不可控（隔離、連線數限制
等），SoftAP 兩台裝置一對一、IP 固定，展示當天比較不會出包。
