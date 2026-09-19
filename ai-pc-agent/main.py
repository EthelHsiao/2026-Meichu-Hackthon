"""AIPC 主程式（分流器），三條路：
1. 觸覺事件：ESP32 本地已處理表情，這裡只更新 state、寫記憶；double_tap 觸發作業拍照流程（見 §5）
2. 截圖：screen_watcher.py（collector -> detector -> VLM -> memory）是獨立程序，不在這裡重複
3. 問答：STT 有文字 或 主動發話規則觸發 -> RAG -> prompt -> MI300 -> 送 SayCommand 給 ESP32
背景另跑 compaction。整體設計見 docs/api.html，決策脈絡見
C:\\Users\\USER\\.claude\\plans\\api-aipc-mi300-arduino-quizzical-aurora.md。
"""
from __future__ import annotations

import asyncio
import subprocess

import cam_client
import config
from chatgpt_bridge import ChatGptBridge
from memory import compaction
from memory.embedder import Embedder
from memory.retrieve import search
from memory.store import MemoryStore
from mi300_client import MI300Client
from prompt import build_messages
from protocol import Heartbeat, SayCommand
from sensing.esp32_ws_client import Esp32WsClient
from sensing.stt import SttBridge
from state import ContextState
from trace_log import TraceLog


def naive_summarize(lines: list[str]) -> str:
    """壓縮期的預設摘要器：先求「不搞丟資訊」，不是「精簡漂亮」。之後要換成真的用
    LLM 摘要時，換掉這個函式、傳進 compaction.run_compaction 就好——介面
    （list[str] -> str，見 memory/compaction.py 的 Summarizer）不用跟著改。"""
    return "；".join(dict.fromkeys(lines))[:200]


class Companion:
    def __init__(self) -> None:
        self.state = ContextState()
        self.memory = MemoryStore(config.DB_PATH, Embedder(config.EMBED_MODEL))
        self.trace = TraceLog()  # 給 debug dashboard 看的測試紀錄，跟 memory 無關
        self.mi300 = MI300Client(base_url=config.MI300_BASE_URL, trace=self.trace)
        self.esp32 = Esp32WsClient(on_event=self._on_esp32_event, on_mic=self._on_mic_frame)
        self.chatgpt = ChatGptBridge()
        self.stt = SttBridge(on_final=self._on_final_utterance)
        self._utterance_queue: asyncio.Queue[str] = asyncio.Queue()
        self._homework_buffer: list[str] | None = None  # None = 不在收集作業逐字稿

    # ---------------- 觸覺 ----------------
    def _on_esp32_event(self, event) -> None:
        if isinstance(event, Heartbeat):
            return
        self.state.last_touch = {"kind": event.kind, "strength": event.strength}
        self.trace.add("touch", {}, {"kind": event.kind, "strength": event.strength, "dur_ms": event.dur_ms})
        self.memory.add_or_extend("touch", f"使用者{event.kind}", state_key="")
        if event.kind == "double_tap":
            self._open_countdown_page()
            asyncio.create_task(self._run_homework_flow())

    def _open_countdown_page(self) -> None:
        """在 AIPC 本機（這支 process 所在的桌面 session）開一個瀏覽器分頁顯示
        5-4-3-2-1 倒數，見 countdown_html.py。跟 _run_homework_flow() 各自獨立計時，
        不用真的同步——倒數頁面本身是純前端計時，長度對齊就好（見該檔案說明）。

        2026-09-20 實測發現 stdlib 的 webbrowser.open() 在這台機器上不可靠：
        它底層呼叫 `gio open`，而這台機器的 Firefox 是 snap 版，gio 沒辦法
        穩定跟已經在跑的 snap-firefox 交握——輕則卡住 20~30 秒才逾時，重則
        安靜地什麼都不做，兩種情況都不會有任何錯誤訊息浮現。改成直接呼叫
        `firefox --new-tab`（使用者從桌面圖示啟動時實際會用到的同一個執行
        檔），這條路徑的交握機制比較可靠，已經實機驗證過真的會開新分頁。
        如果之後這台機器換了預設瀏覽器，這裡要跟著改。"""
        try:
            subprocess.Popen(
                ["firefox", "--new-tab", config.HOMEWORK_COUNTDOWN_URL],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as exc:  # noqa: BLE001 — 開瀏覽器失敗不該擋到後面的拍照分析
            print(f"[homework] 開啟倒數頁面失敗: {exc}")

    # ---------------- 麥克風 -> STT ----------------
    def _on_mic_frame(self, pcm: bytes) -> None:
        asyncio.create_task(self.stt.send_pcm_int16(pcm))

    def _on_final_utterance(self, text: str) -> None:
        # 作業拍照流程期間，使用者的話是拍照逐字稿，不該被當成一般對話觸發回覆。
        routed_to = "homework" if self._homework_buffer is not None else "reply"
        self.trace.add("stt_final", {}, {"text": text, "routed_to": routed_to})
        if self._homework_buffer is not None:
            self._homework_buffer.append(text)
        else:
            self._utterance_queue.put_nowait(text)

    async def _say(self, expr: str, text: str) -> None:
        """送 SayCommand 給 ESP32；連不上（還沒連線／斷線中）不能讓呼叫端的背景
        迴圈跟著死掉——這幾條迴圈全部掛在同一個 asyncio.gather()，任何一個沒接住
        的例外會把其他兩條也一起拖死（截圖記憶、對話回覆、壓縮全部停擺）。"""
        try:
            await self.esp32.send(SayCommand(expr=expr, text=text))
            self.trace.add("esp32_say", {"expr": expr, "text": text}, {"sent": True})
        except Exception as exc:  # noqa: BLE001
            print(f"[esp32] 送出失敗（可能還沒連線): {exc}")
            self.trace.add("esp32_say", {"expr": expr, "text": text}, {"sent": False, "error": str(exc)})

    # ---------------- 對話回覆 ----------------
    async def _reply_loop(self) -> None:
        while True:
            user_text = await self._utterance_queue.get()
            try:
                await self._reply(user_text)
            except Exception as exc:  # noqa: BLE001 — 這一輪回覆失敗不能讓整條迴圈停掉
                print(f"[reply] 處理失敗: {exc}")

    async def _reply(self, user_text: str) -> None:
        recent = [m.line() for m in self.memory.recent(config.RECENT_N)]
        related = [hit.memory.line() for hit in search(self.memory, user_text or self.state.activity)]
        messages = build_messages(
            self.state, recent, related, user_text,
            facts=self.memory.facts(), touch=self.state.last_touch,
        )
        try:
            result = self.mi300.reply(messages)
        except Exception:  # noqa: BLE001 — MI300 連不上不能卡住 demo，用本機 fallback
            result = {"expr": "neutral", "text": "我在，訊號有點不穩，等我一下"}
        self.memory.add_or_extend("reply", result["text"], state_key="")
        await self._say(result.get("expr", "neutral"), result["text"])

    # ---------------- 作業拍照分析（FSR1 雙擊 -> 拍照 -> ChatGPT，見 docs/api.html §⑥）----------------
    async def _run_homework_flow(self) -> None:
        try:
            self._homework_buffer = []
            # 5-4-3-2-1 倒數本身的畫面 UI 是前端另外的工作，這裡只負責等同樣長度的
            # 時間、同時收集這段時間內使用者說的話，倒數結束的瞬間視覺與這裡的計時
            # 應該對齊。
            await asyncio.sleep(5)
            transcript = " ".join(self._homework_buffer)
            self._homework_buffer = None

            try:
                image_bytes = cam_client.capture_snapshot()
                self.trace.add("cam_snapshot", {}, {"ok": True}, image_bytes=image_bytes)
            except Exception as exc:  # noqa: BLE001
                self.trace.add("cam_snapshot", {}, {"ok": False, "error": str(exc)})
                raise
            result = self.mi300.analyze_homework(image_bytes, transcript)
            self.memory.add_or_extend("homework", result["analysis"], state_key="")

            reassurance = result["reassurance"]
            await self._say(reassurance.get("expr", "neutral"), reassurance["text"])

            try:
                await self.chatgpt.send_prompt(result["chatgpt_prompt"])
                self.trace.add("chatgpt_send", {"prompt": result["chatgpt_prompt"]}, {"sent": True})
            except Exception as exc:  # noqa: BLE001 — Playwright 失敗不能讓整個流程掛掉，留 log 就好
                print(f"[homework] 送到 ChatGPT 失敗: {exc}")
                self.trace.add("chatgpt_send", {"prompt": result["chatgpt_prompt"]}, {"sent": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001 — 這是用 create_task() 丟出去的背景任務，
            # 沒有人在等它，例外不會自動被看到，一定要在這裡自己接住並留 log。
            print(f"[homework] 流程失敗: {exc}")
        finally:
            self._homework_buffer = None

    # ---------------- 背景壓縮 ----------------
    async def _compaction_loop(self) -> None:
        while True:
            await asyncio.sleep(config.COMPACT_CHECK_EVERY_MIN * 60)
            try:
                compaction.run_compaction(self.memory, naive_summarize)
            except Exception as exc:  # noqa: BLE001 — 這一輪壓縮失敗不能讓整條迴圈停掉
                print(f"[compaction] 失敗: {exc}")

    async def run(self) -> None:
        try:
            await self.stt.connect()
        except Exception as exc:  # noqa: BLE001 — STT 服務沒起來時，其他流程還是要能跑
            print(f"[stt] 連線失敗，語音回覆會停擺，其他功能不受影響: {exc}")

        await asyncio.gather(
            self.esp32.run_forever(),
            self._reply_loop(),
            self._compaction_loop(),
        )


def main() -> None:
    asyncio.run(Companion().run())


if __name__ == "__main__":
    main()
