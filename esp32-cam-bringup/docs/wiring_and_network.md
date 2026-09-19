# ESP32-CAM 接線、燒錄、共用熱點傳輸

這塊板子是**獨立的第二顆 ESP32**，跟主板 `esp32-bringup`（FSR/IMU/LCD/蜂鳴器/麥克風）
完全分開，只接相機，不接任何其他零件——這是你已經確認的限制。

---

## 一、相機本身怎麼接

相機排線（OV2640）已經**直接焊在 / 插在**板子上對應的排線座，腳位由
`include/camera_pins.h` 固定（那些是模組出廠就決定的接點，不是你可以自己選的接線）。
你唯一要處理的接線是：**供電**跟**燒錄用的序列線**，下面兩節分別說明。

## 二、供電——這是 ESP32-CAM 最容易踩坑的地方

ESP32-CAM **沒有內建 USB 介面**（跟你主板的 DevKit V1 不一樣），只有排針，
所以：

1. **開發/燒錄時**需要外接一顆 USB 轉序列（USB-TTL）轉接板（例如 CP2102 或
   FTDI 模組——不是你主板那顆焊死在板子上的，是額外一顆獨立小板）。
2. **供電務必走轉接板的 5V 腳，不要走 3.3V 腳。** ESP32-CAM 板上自己有
   穩壓器把 5V 降到相機跟晶片要的電壓；很多便宜 USB-TTL 轉接板的
   3.3V 輸出電流不夠（相機啟動、WiFi 傳輸時會有瞬間大電流），
   接 3.3V 常常導致開機重開機迴圈或相機初始化失敗，症狀很像接線錯誤
   但其實是電流不夠。
3. 接線對照（轉接板 → ESP32-CAM）：

   | 轉接板 | ESP32-CAM |
   |---|---|
   | 5V | 5V |
   | GND | GND |
   | TX | U0R（也標 RX / GPIO3）|
   | RX | U0T（也標 TX / GPIO1）|

   注意 TX 接 RX、RX 接 TX，是交叉接，不是同名對同名。

## 三、燒錄模式——GPIO0 短接 GND

ESP32-CAM 沒有自動下載電路（跟你主板的 DevKit V1 不一樣，那塊板子插 USB
接電腦就能直接燒錄），**每次要燒錄新程式之前**：

1. 用一條杜邦線把 **GPIO0 短接到 GND**（板上通常兩個都有獨立排針，或旁邊
   有一個叫 `IO0` 的洞）。
2. 按一下 RST（重置）鍵，或重新插拔供電，讓它在按住 GPIO0-GND 短接的狀態下開機。
3. 在 PlatformIO 執行 Upload（`cam_stream` 這個 env）。
4. **燒錄完成後，把 GPIO0-GND 的短接線拔掉**，再按一次 RST，板子才會正常開機
   執行程式，而不是又進燒錄模式待機。

沒拔掉那條線的症狀：燒錄看似成功，但開機後 Serial Monitor 什麼都不印、
程式沒有在跑——這不是程式錯誤，先檢查 GPIO0 是不是還接著 GND。

## 四、共用熱點傳輸——為什麼要改，怎麼改

### 為什麼原本的做法行不通

主板 `esp32-bringup` 的 `s9_wifi_sensors` 預設是**自己開一個 Wi-Fi 熱點**
（SoftAP，SSID `ESP32-Companion`），電腦直接連上這個熱點。這在只有一塊
ESP32 時沒問題，但現在多了 ESP32-CAM 這第二塊板子：**你的電腦 Wi-Fi 網卡
一次只能連一個 Wi-Fi 網路**，沒辦法同時連「主板的熱點」跟「CAM 板的熱點」——
這是筆電/手機 Wi-Fi 網卡的實體限制，不是設定沒調好。

### 解法：兩塊 ESP32 都改成「加入同一個外部熱點」

用一個外部熱點（手機熱點，或現場的路由器）當共同的家，主板、CAM 板、
電腦三方都用 STA 模式加入**同一個** Wi-Fi 網路，彼此就能用區網內的 IP
互相連線，不再需要輪流切換電腦要連哪一台 ESP32 的熱點。

**步驟：**

1. 準備一個 **2.4GHz** 的熱點（ESP32 系列都不支援 5GHz），記下 SSID 跟密碼。
   手機熱點記得檢查是不是預設開了 5GHz 或雙頻，需要切成 2.4GHz 專用或雙頻同名。

2. **主板** `esp32-bringup`：
   - 把 `include/telemetry_local.example.h` 複製一份成 `include/telemetry_local.h`
     （這個檔名已經在 `.gitignore` 裡，不會進 git）。
   - 打開 `telemetry_local.h`，改成：
     ```
     #define TELEMETRY_USE_STA 1
     #define TELEMETRY_STA_SSID "你的熱點名稱"
     #define TELEMETRY_STA_PASSWORD "你的熱點密碼"
     ```
   - 用 `s9_wifi_sensors` 這個 env 重新 Build + Upload。開機後 Serial Monitor
     會印出它拿到的 IP（`Dashboard: http://<IP>/`）。

3. **CAM 板** `esp32-cam-bringup`（這個專案）：
   - 把 `include/cam_wifi_local.example.h` 複製一份成 `include/cam_wifi_local.h`。
   - 填入**同一個**熱點的 SSID/密碼：
     ```
     #define CAM_WIFI_SSID "你的熱點名稱"
     #define CAM_WIFI_PASSWORD "你的熱點密碼"
     ```
   - 用 `cam_stream` 這個 env Build + Upload。開機後 Serial Monitor 一樣會印出
     它拿到的 IP。

4. **電腦**：直接連上同一個熱點（跟平常連 Wi-Fi 一樣，不用改任何程式）。

5. 三方都在同一個區網之後：
   - 瀏覽器打開 `http://<主板IP>/` 看 FSR/IMU 的內嵌測試頁。
   - 瀏覽器打開 `http://<CAM板IP>/` 看即時畫面（MJPEG 串流）。
   - 兩個 IP 是各自獨立的，不會互相干擾；哪塊板子重開機、IP 可能會變，
     以它重開機後 Serial Monitor 印出的最新 IP 為準（除非之後在熱點上
     設定固定 IP／保留位址）。

6. 黑客松現場建議：**不要用場館 Wi-Fi 當這個共用熱點**，用一支手機開熱點
   專門給這三個裝置用，比較不會遇到場館網路的 client isolation（同網段裝置
   互相看不到彼此）或連線數限制問題。電腦如果同時還需要連場館網路做別的事
   （例如你們的 `mi300-deploy`／`ai-pc-agent` 那邊要連的服務），可以用網路線
   接場館網路、Wi-Fi 網卡專門連這個手機熱點，兩條路徑分開走。

## 五、測試步驟（單獨驗證，不急著串到主板）

1. 先只接供電 + 燒錄線，不用先想共用熱點的事——用你自己家裡/手機的任一個
   熱點就能先測「相機會不會動」。
2. Build + Upload `cam_stream`，開 Serial Monitor 看有沒有印出
   `Camera init: OK` 跟拿到的 IP。
3. `Camera init: FAILED` 通常是排線沒插好/方向反了，或供電不夠（見第二節），
   不是程式問題。
4. 瀏覽器開 `http://<IP>/`，應該看到即時畫面；`http://<IP>/api/v1/cam/snapshot`
   是單張快照，`http://<IP>/api/v1/health` 是健康狀態 JSON——三個都能動
   再進下一步（串進共用熱點、跟主板一起測）。
