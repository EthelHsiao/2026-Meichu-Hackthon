# 待實作功能 — 交接規格

給接手的 agent/人看的。每一項都包含現況、要動的檔案、明確的介面/合約、以及怎麼驗證。
整體架構背景見 `docs/api.html` 跟 `C:\Users\USER\.claude\plans\api-aipc-mi300-arduino-quizzical-aurora.md`。

---

## 1. 手勢偵測：squeeze / pat / shake / lift / putdown

**現況**：`esp32-bringup/include/companion_app.h` 只有 `fsr1DetectDoubleTap()` 這一個手勢的偵測邏輯（壓 FSR1 兩下）。其他 5 種手勢完全沒有韌體端偵測程式碼——只在 `ai-pc-agent/protocol.py` 的 `TouchKind` 型別跟 `docs/api.html` §① 裡定義了訊息格式，AIPC 那端已經能解析，缺的是「韌體怎麼從 FSR/IMU 原始訊號判斷發生了哪一種手勢」。

**要動的檔案**：`esp32-bringup/include/companion_app.h`（在 `companionSampleSensors()` 裡，`fsr1DetectDoubleTap` 呼叫旁邊加新的偵測函式）

**輸出合約**（已經定案，不用改）：
```json
{"t":"touch","kind":"squeeze"|"pat"|"shake"|"lift"|"putdown","strength":0.0-1.0,"dur_ms":<int>}
```
用 `companionWs.broadcastTXT(...)` 送出，跟 `double_tap` 那行一樣的寫法。

**可用的感測器輸入**：
- FSR1（`PIN_FSR1_SENSE`=GPIO34）、FSR2（`PIN_FSR2_SENSE`=GPIO35），12-bit ADC，50Hz 取樣
- IMU 加速度/角速度（`companionMpu.getEvent()` 或 raw fallback，見同檔案的 `companionSampleSensors()`）

**建議的判斷方向**（沒有實測驗證過，需要實機拿真的動作去调）：
- `squeeze`：FSR1+FSR2 同時超過某個高閾值、且維持一段時間（跟 double_tap 的「短暫按放兩次」明顯不同節奏）
- `pat`：單一短暫的 FSR 尖峰（一次，不是兩次）
- `shake`：短時間窗內 IMU 加速度變化量（peak-to-peak 或 variance）超過閾值
- `lift`/`putdown`：IMU 加速度 z 軸或姿態的持續性變化（離開桌面 vs 放回桌面的兩種穩定狀態）

**怎麼校準/驗證**：用 `esp32-bringup/tools/receive_telemetry.py` 接上 WebSocket，實際做每個動作、記錄原始 FSR/IMU 數值，用真實數字定閾值（跟 `board_config.h` 裡 FSR_FIXED_R_OHM 從 10k 換成 47k 那次校準是同樣的方法論）。定案後回頭把 `FSR1_PRESS_THRESHOLD` 等常數的 `[CANDIDATE]` 標記改成 `[CONFIRMED]`。

---

## 2. double_tap 閾值校準

**現況**：`FSR1_PRESS_THRESHOLD = 2048`（12-bit ADC 中點）是純猜的，`companion_app.h` 裡標記為 `[CANDIDATE]`，從沒拿真實按壓數值驗證過。

**要動的檔案**：`esp32-bringup/include/companion_app.h` 的 `FSR1_PRESS_THRESHOLD`、`FSR1_DEBOUNCE_MS`、`FSR1_DOUBLE_TAP_WINDOW_MS`

**驗證方法**：同上，接 `receive_telemetry.py`，實際壓兩下 FSR1，記錄真實 raw ADC 值調整閾值；同時測「誤觸發率」（正常打字/移動裝置會不會誤判成雙擊）。

---

## 3. LCD 韌體整合與新表情視覺驗證

**現況**：`esp32-bringup/include/lcd_faces.h` 寫好了全部 9 種表情（`neutral/happy/joy/love/sad/sleepy/surprised/thinking/worried`），但整份 `s13_companion` build **完全沒有編譯、燒錄、在實機跑過**。新增的 `neutral`/`thinking`/`worried` 三種畫法（眉毛、瞳孔偏移、波浪嘴巴）完全是憑空設計，沒人看過實際畫出來長怎樣。

**要動的檔案**：`esp32-bringup/include/lcd_faces.h`（畫面微調）

**驗證方法**：
1. PlatformIO 選 `s13_companion` env，Build → Upload
2. 用 WebSocket 送 `{"t":"expr","expr":"<每一種名字>"}` 逐一測試（可以用 `ai-pc-agent/sensing/esp32_ws_client.py` 寫個小腳本，或用任何 WebSocket 測試工具連 `ws://<esp32-ip>:81/api/v1/stream` 送文字訊息）
3. 肉眼確認每張臉的表情辨識度、有沒有殘影（換表情時舊畫面沒清乾淨）

---

## 4. 5-4-3-2-1 拍照倒數 UI — ✅ 已完成（2026-09-20）

`ai-pc-agent/countdown_html.py`（頁面本身：相機預覽 + 純前端倒數 + 輪詢 `/debug/trace` 顯示結果）、`debug_api.py` 的 `GET /homework-countdown`（服務這個頁面）、`main.py` 的 `_on_esp32_event` 偵測到 `double_tap` 時呼叫 `_open_countdown_page()`（`webbrowser.open(config.HOMEWORK_COUNTDOWN_URL)`），跟 `_run_homework_flow()` 平行各自計時，不強求同步。

**驗證方法**：`POST /debug/gesture {"kind":"double_tap"}` 應該在 AIPC 桌面（跑 `ai-pc-agent-dashboard.service` 的那個 Xorg session）真的開一個瀏覽器分頁，5 秒倒數後顯示「分析中」，再等 MI300 回應後顯示 `reassurance` 文字跟 ChatGPT 送出狀態。**沒有實機驗證過的部分**：相機真的接上時 MJPEG 串流顯示效果、倒數視覺跟後端拍照時間點的實際誤差。

---

## 5. 啟動 STT 服務

**現況**：`stt/backend/main.py` 這支服務程式碼已經有、也有自己的 `.venv`（`stt/.venv`，已確認存在於 AIPC 上），但目前沒有任何地方啟動它。`ai-pc-agent/config.py` 的 `STT_WS_URL` 預設指向 `ws://127.0.0.1:8765/ws/audio`，跟 `stt/backend/main.py` 的預設埠一致，不用改設定。

**啟動方式**（在 AIPC 上）：
```bash
cd ~/2026-Meichu-Hackthon/stt/backend
source ../.venv/bin/activate   # 或看 stt/README.md 實際的 venv 路徑
python -m uvicorn main:app --host 127.0.0.1 --port 8765
```

**驗證方法**：啟動後 `curl http://127.0.0.1:8765/healthz` 應該回 `{"status":"ok",...}`；`ai-pc-agent` 的 `debug_api`／`main.py` 重啟後 `/debug/status` 就不會再印 `[stt] 連線失敗` 的訊息。真正測語音要接麥克風（目前沒有 ESP32 硬體，暫時測不了；純軟體驗證可以參考 `stt/backend` 自己的測試腳本）。

---

## 6. 主動關心觸發策略

**現況**：`ai-pc-agent/detector.py` 的 `ChangeDetector` 有 `idle_threshold`／`min_vlm_seconds` 邏輯，但只用在「要不要把這次截圖送去 MI300」（`screen_watcher.py`），沒有任何地方用它來決定「桌寵要不要主動開口講話」。`ai-pc-agent/prompt.py` 的 `build_messages()` 已經設計成 `user_text=""` 代表主動發話（system prompt 裡會告訴 MI300 這是主動情境），這個介面已經就緒，只是沒有東西去呼叫它。

**要動的檔案**：`ai-pc-agent/main.py`（新增一個背景迴圈，比照 `_compaction_loop()` 的寫法）

**建議做法**：
```python
async def _proactive_loop(self) -> None:
    while True:
        await asyncio.sleep(60)  # 或其他檢查頻率
        if <判斷「卡在同一個狀態太久」的條件，可以參考 self.state.error/error_since>:
            await self._reply("")  # 空字串 = 主動發話
```
判斷條件需要設計（例如：`self.state.error` 存在且 `datetime.now() - self.state.error_since > 某個門檻`），`state.py` 的 `ContextState` 已經有 `error_since`/`activity_since` 欄位可以用，但目前沒有任何程式碼在寫入這兩個欄位（`main.py`/`screen_watcher.py` 都沒有更新 `self.state.error`/`activity` — 這也要一起補，不然這個功能沒有資料可以判斷）。

**驗證方法**：用 `/debug/utterance` 或直接操作 `companion.state` 手動製造「卡住很久」的情境，觀察是否在下一個檢查週期收到主動回覆（`/debug/trace` 應該出現 `chat_reply`，`request.messages` 裡的 `【使用者說】` 應該是「（沒有，這是主動發話）」）。

---

## 7. profile 自動學習（使用者說「記住...」）

**現況**：`ai-pc-agent/memory/store.py` 的 `add_fact()`/`remove_fact()` 已經寫好且有測試，但沒有任何程式碼呼叫它。使用者說「記住我在做 ESP32 專案」這種話，目前只會被當成普通對話處理，不會真的存進 `profile` 表。

**要動的檔案**：`ai-pc-agent/main.py`（`_on_final_utterance` 或 `_reply` 裡加判斷）

**建議做法**：最簡單的版本——偵測 STT 文字是否以「記住」開頭，如果是就把後面的內容當 fact 存起來（`self.memory.add_fact(text.removeprefix("記住").strip())`），不觸發一般對話回覆；更進階的版本可以交給 MI300 判斷「這句話是不是在講一個該記住的事實」，但那需要在 MI300 加新的分類邏輯，目前完全沒有。

**驗證方法**：`/debug/utterance` 送 `{"text": "記住我在做 ESP32 桌寵專案"}`，然後檢查 dashboard 的記憶列表（目前 `/debug/memory/recent` 只列 `memories` 表，沒有列 `profile` 表——如果要在 dashboard 驗證，也要加一個 `/debug/profile` endpoint）。

---

## 8. 真的用 LLM 做記憶壓縮摘要

**現況**：`ai-pc-agent/main.py` 的 `naive_summarize()` 只是把不重複的句子用「；」接起來、截斷到 200 字，不是真的摘要，只是先求「不搞丟資訊」。`memory/compaction.py` 的 `run_compaction(store, summarize, ...)` 介面已經定義好（`Summarizer = Callable[[list[str]], str]`），要換真的摘要器只要寫一個新函式符合這個介面、在 `Companion._compaction_loop()` 裡换掉 `naive_summarize` 就好，不用動 `compaction.py`。

**要動的檔案**：`ai-pc-agent/main.py`（新增一個 summarizer 函式，換掉 `_compaction_loop` 裡傳給 `run_compaction` 的那個參數）

**建議做法**：呼叫 MI300，但**不要**用 `/v1/chat/completions`（那支是為了「表情+短回覆」設計的，會被 40 字截斷、還會被 JSON 格式綁死）。要嘛在 MI300 加一支新的、專門給「一段對話紀錄 -> 一段摘要文字」用的端點，要嘛先確認要不要重用 MI300 舊有的 `/analyze/screen` 之類的通用呼叫方式（目前沒有現成的「純文字摘要」端點）。

**驗證方法**：把 `config.COMPACT_AFTER_HOURS` 臨時調小（例如 0.01），塞幾筆超過門檻時間的假記憶（可以用 `/debug/memory/seed` 的資料改一下時間戳），觀察 `memories` 表裡 `level='raw'` 的記錄是否被正確壓縮成 `level='summary'`。

---

## 9. 截圖 pipeline 需要有人登入 AIPC 桌面

**不是程式碼問題，是環境現況**：2026-09-20 實測發現 AIPC（`172.17.46.226`）目前透過 SSH 進去沒有 `DISPLAY` 環境變數，且 `loginctl list-sessions` 顯示 seat0/tty2 停在「login screen」——目前沒有人實際登入圖形桌面。`mss`（screenshot.py 用的截圖套件）需要能存取 X11 display 才能抓螢幕，`xdotool`/`xprop`（collectors.py 用來讀前景視窗）也一樣。

**要做的事**：有人實際登入 AIPC 的桌面（本機操作或遠端桌面皆可）之後：
1. 確認 `echo $DISPLAY` 在該桌面 session 裡有值（通常是 `:0` 或 `:1`）
2. 從那個桌面環境本身開一個終端機（不是另外 SSH 進去），跑 `python screen_watcher.py`（獨立持續執行的截圖迴圈）或啟動整個 `main.py`/`debug_api.py`，這樣才會自動繼承正確的 `DISPLAY`
3. 如果堅持要從 SSH 操作，需要先 `export DISPLAY=:0`（實際數字要現場確認）跟可能的 `XAUTHORITY`，但這條路徑沒驗證過能不能通（要看是 X11 還是 Wayland、xauth 權限設定）

**驗證方法**：`POST /debug/screenshot` 應該回傳有真實 `app`/`window_title` 的 `foreground` 欄位（不再是全部 `null`），dashboard 的 trace 應該出現 `screen_observation` 紀錄。
