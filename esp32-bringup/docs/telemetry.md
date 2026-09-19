# Step 9：用 Wi-Fi 把 FSR / MPU6050 傳到電腦

這是 Arduino framework 下的 ESP32 測試，不需要 MI300。
新增的 PlatformIO environment 是 **`s9_wifi_sensors`**。

## 通訊方式

```text
FSR ×2 + MPU6050 → ESP32（HTTP / WebSocket server）
                            ⇅ Wi-Fi
                  電腦（瀏覽器 / Python client）
```

電腦先發起連線，ESP32 就能在同一條 WebSocket 上主動傳資料。
不需要先在電腦架 HTTP server。誰開 Wi-Fi 熱點，與誰是 API server，是兩件事。

- HTTP：一個 request 對一個 response，適合查狀態、讀最新一筆。
- WebSocket：先經過 HTTP Upgrade 握手，之後傳 WebSocket 訊息，適合持續感測資料和雙向指令。不是反覆發 HTTP POST。
- 預設每 50 ms 取樣並推送一次（目標 20 Hz，不是硬即時保證）。HTTP 與 WebSocket 共用最新一筆資料。

## 最短驗收流程：電腦連 ESP32 熱點

1. 沿用已驗證的接線：FSR1 sense → GPIO34、FSR2 sense → GPIO35；MPU6050 SDA → GPIO21、SCL → GPIO22，位址 `0x68`。供電與共地沿用原有接線文件。
2. VS Code 開啟 `esp32-bringup` 資料夾，在 PlatformIO → Project Tasks → **s9_wifi_sensors** 執行 **Build → Upload → Monitor**。USB 用來燒錄及供電，之後感測資料走 Wi-Fi。Monitor 為 115200 baud。
3. 電腦連上 `ESP32-Companion`，密碼沿用 `board_config.h`（目前 `12345678`）。Windows 顯示「無網際網路」不影響這條區域網路連線。
4. 瀏覽器開 **`http://192.168.4.1/`**，看即時數值。不需要安裝 Python 才能看。
5. 分別按壓 FSR1 / FSR2，確認對應數值變動；轉動 MPU6050，確認加速度／角速度變動。按「測試雙向 ping」，應顯示收到 pong。
6. 做 60 秒記錄（下面有指令），關閉、重新連上 Wi-Fi，確認接收器會重連。

PlatformIO 終端機的等價指令（工作目錄為 `esp32-bringup`）：

```powershell
pio run -e s9_wifi_sensors
pio run -e s9_wifi_sensors -t upload
pio device monitor -b 115200
```

若一般 PowerShell 找不到 `pio`，用 PlatformIO 提供的終端機或上述 Project Tasks。
若 Upload 顯示 COM 被佔用，先關閉 Serial Monitor。

## 若你開的是電腦／手機熱點

在 `esp32-bringup` 下執行：

```powershell
Copy-Item include/telemetry_local.example.h include/telemetry_local.h
```

編輯 `telemetry_local.h`：

```cpp
#define TELEMETRY_USE_STA 1
#define TELEMETRY_STA_SSID "你的熱點名稱"
#define TELEMETRY_STA_PASSWORD "你的熱點密碼"
```

使用 2.4 GHz 熱點；電腦與 ESP32 要能在同一網路互相連線。重新 Build / Upload，
在 Serial Monitor 找 `Dashboard: http://實際IP/`，把本文的 `192.168.4.1` 全部換成這個 IP。
在這個模式下 ESP32 不會開 `ESP32-Companion` 熱點。Wi-Fi 斷線會重試，重新取得 IP 時會印出。
`telemetry_local.h` 已加入 Git ignore，熱點密碼不應提交到 Git。

若只測網路、感測器還沒接上，可在本機設定檔將
`TELEMETRY_FSR_ENABLED` / `TELEMETRY_IMU_ENABLED` 設為 `0`；封包會回 `null`，不會生成假感測值。
FSR 開啟但未接線時，ADC 可能浮動，程式無法據此確認 FSR 是否存在。

## HTTP 測試與 API v1

```powershell
curl.exe --noproxy "*" http://192.168.4.1/api/v1/health
curl.exe --noproxy "*" http://192.168.4.1/api/v1/telemetry
```

| 介面 | 位址 | 用途 |
|---|---|---|
| HTTP GET | `http://<ESP32-IP>/` | 即時測試頁，頁面自動連 WebSocket |
| HTTP GET | `http://<ESP32-IP>/api/v1/health` | server 狀態、裝置 ID、Wi-Fi 模式、IMU 最近讀取狀態 |
| HTTP GET | `http://<ESP32-IP>/api/v1/telemetry` | 最新一筆感測 JSON，不會另外觸發一次取樣 |
| WebSocket | `ws://<ESP32-IP>:81/api/v1/stream` | 連線時先送最新一筆，之後持續推送 |

HTTP 成功回 `200`；未知路徑或不支援的方法回 `404` / `not_found`。
WebSocket 路徑不符時會在握手後關閉。HTTP 的 `health.ok=true` 表示 server 可回應，**不代表所有感測器正常**；看 `imu_ok` 與 telemetry 欄位。

WebSocket client 可送**文字訊息** `ping`（四個字元，不是 JSON 字串的雙引號）：

```json
{"schema_version":1,"type":"pong"}
```

其他文字指令回 `{"schema_version":1,"type":"error","code":"unsupported_command"}`。
v1 不支援 binary / fragmented application messages；一般短 JSON / `ping` 使用單一 text frame。
這是應用層雙向測試，與 WebSocket 協定本身的 ping/pong 心跳不同。
韌體另有協定心跳以清理失聯 client。

### 感測封包

以下數字僅示範格式，**不是實測值**：

```json
{
  "schema_version": 1,
  "type": "telemetry",
  "device_id": "esp32-001122334455",
  "boot_id": "a1b2c3d4",
  "seq": 42,
  "uptime_ms": 3200,
  "sample_period_ms": 50,
  "fsr": {"enabled": true, "raw": [120, 230]},
  "imu": {
    "ok": true,
    "status": "ok",
    "accel_m_s2": [0.1, -0.2, 9.8],
    "gyro_rad_s": [0.01, 0.02, -0.01],
    "temperature_c": 27.5
  }
}
```

| 欄位 | 定義 |
|---|---|
| `schema_version` | 目前固定 `1`，不相容改動需升版 |
| `device_id` | 晶片 MAC 衍生的裝置識別 |
| `boot_id` | 每次開機隨機 ID，協助辨識重啟，非安全憑證 |
| `seq` | 每次取樣遞增，32-bit 溢位後回 0；重啟從 1 開始 |
| `uptime_ms` | 取樣開始時的裝置 millis，不是 Unix 時間；約 49.7 天回繞 |
| `sample_period_ms` | 設定的取樣間隔；實際間隔可能因 I/O 延遲變長 |
| `fsr.raw` | `[FSR1, FSR2]`，12-bit ADC 0–4095，未校準為 N / kg / 壓力 |
| `imu.accel_m_s2` | `[x,y,z]` 加速度，m/s²，包含重力 |
| `imu.gyro_rad_s` | `[x,y,z]` 角速度，rad/s，不是姿態角 |
| `imu.temperature_c` | MPU6050 晶片溫度 °C |

IMU 初始化失敗時 `ok=false, status="not_found"`；取樣前 I2C 探測失敗或回傳無效值時為 `read_failed`；停用時為 `disabled`。
上述三種情況的加速度、角速度與溫度皆為 `null`。初始化失敗後修正接線需重新啟動板子。
I2C 探測與有限值檢查不等於完整的感測器故障診斷或校準。

## 在電腦接收、存檔

需要 Python 3.11+。以下從 `esp32-bringup` 執行：

```powershell
python -m venv tools/.venv
tools/.venv/Scripts/python.exe -m pip install -r tools/requirements.txt
tools/.venv/Scripts/python.exe tools/receive_telemetry.py --duration 60 --output logs/telemetry.jsonl
```

STA 模式指定實際 IP：

```powershell
tools/.venv/Scripts/python.exe tools/receive_telemetry.py --url ws://192.168.137.123:81/api/v1/stream --output logs/telemetry.jsonl
```

`192.168.137.123` 僅為例子，請以板子印出的 IP 為準。
不帶 `--duration` 會持續到 Ctrl+C。接收器每秒顯示摘要，逐筆追加寫入 JSONL，
每行包含電腦端 UTC `received_at` 與原始 `sample`。網路斷線或 5 秒無資料會重連；
格式錯誤的封包會忽略；`--duration` 到期但完全沒收到有效資料時會以失敗狀態結束。

`sequence_gaps` 是同一次開機收到的 seq 間缺口，包含離線期间錯過的取樣，**不是 Wi-Fi 封包掉包率**。
重连時相同 seq 的快取封包會去重。ESP32 不儲存或補送離線資料；電腦接收時間也不等於單向延遲。

## 驗收與排錯

- 頁面有新封包、seq 持續遞增：網路傳輸通了。
- 分別按壓兩個 FSR，只有對應讀值明顯改變：兩路壓感器通了。
- 移動／旋轉 IMU，加速度與角速度有變化、`imu.ok=true`：IMU 讀取通了；靜止時一軸附近出現重力值是正常現象。
- 收到 pong：電腦 → ESP32 → 電腦雙向通了。
- JSONL 有持續新增記錄：資料已進入電腦。
- 拔 USB 做無線驗收前，先提供已確認合適的獨立電源；USB 拔掉若整板斷電，不是 Wi-Fi 問題。

HTTP 連不上時先確認電腦連對 SSID、IP 與 Serial 顯示一致、沒有 VPN / proxy 攔截區域網路。
共享熱點若開了 client isolation，可能同網路卻不能互連。HTTP 通但 WS 不通時檢查 port `81` 與 path；
若還燒著 Stage 8，它只在 `/` 傳 `hb`，不支援此 v1 協定。
接收器是主動向外連 ESP32，不需要在電腦開接收 port。

這一版是區域網路開發測試，API 沒有登入驗證，使用明文 HTTP / WS；部署到不受信任網路前再設計認證與 TLS。

## 後續 API 擴充方向（尚未實作）

保持感測串流與命令分開定義：例如未來的 `POST /api/v1/display` 設定 LCD、
`GET /api/v1/config` 查設定，或 WebSocket `type="command"` 搭配 `request_id`，回 `ack` / `error`。
具體欄位應等 LCD／狀態機行為確定後再定義，避免前後端各自猜測。
AI PC 後續可讀本接收器相同的 WebSocket，把必要事件送 MI300 API。

## 本次驗證紀錄

- `LEVEL_COMPILE`：`pio run -e s9_wifi_sensors` 成功。
- `LEVEL_SIM`：`python -m unittest discover -s tools -p test_receive_telemetry.py -v`，4 項通過，包含實際 localhost WebSocket 握手、ping、重連、重啟、seq 缺口、JSONL 存檔與期限控制。
- `LEVEL_HW`：尚未完成。需燒錄後，以真實按壓／移動驗收，不能將模擬測試當作實測。

介面參考：[Espressif Wi-Fi API](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/wifi.html)、
[websockets 12.0 client API](https://websockets.readthedocs.io/en/12.0/reference/asyncio/client.html)。
