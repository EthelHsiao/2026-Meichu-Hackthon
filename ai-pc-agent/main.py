"""AIPC 主程式（分流器），三條路：
1. 觸覺事件：ESP32 本地已處理表情，這裡只更新 state、寫記憶
2. 截圖：screen_watcher.py（collector -> detector -> VLM -> memory），更新 state
3. 問答：STT 有文字 或 主動發話規則觸發 -> RAG -> prompt -> MI300 -> 送 SayCommand 給 ESP32
背景另跑 compaction。"""


def main():
    raise NotImplementedError


if __name__ == "__main__":
    main()
