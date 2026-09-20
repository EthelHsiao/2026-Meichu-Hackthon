"""把作業分析流程產生的 chatgpt_prompt 貼進使用者「已經開好」的 ChatGPT 分頁並送出
（見 docs/api.html §⑥）。用 connect_over_cdp 接上使用者現有的瀏覽器，不是另外開一個
自動化瀏覽器——使用者的 Chrome 需要先用 remote-debugging-port 啟動，例如：
    chrome.exe --remote-debugging-port=9222

用 Playwright 的 async API（不是 sync API）：這支模組永遠在 asyncio 環境裡被呼叫
（main.py 的 Companion、debug_api.py 的 FastAPI endpoint 都跑在同一個 event loop
上），Playwright 的 sync API 明確禁止在已經有 event loop 在跑的情況下使用，
實測會直接拋 "It looks like you are using Playwright Sync API inside the asyncio
loop" 錯誤，2026-09-20 用真的 Chrome 測 /debug/homework 時親自撞到過。

這是全新模組，repo 裡目前沒有其他 Playwright 程式碼可以參考。ChatGPT 網頁的 DOM
選取器會隨改版變動、這裡的選取器沒有在真實網頁上跑過，實作完要先手動用
POST /debug/homework 對著真的開著的 ChatGPT 分頁測一次，不保證長期有效
（這點在計畫的「這份設計不會解決的問題」第 6 點已經寫明）。
"""
from __future__ import annotations

CHATGPT_URL_FRAGMENTS = ("chat.openai.com", "chatgpt.com")
COMPOSER_SELECTOR = 'div#prompt-textarea, textarea[data-id="root"]'


class ChatGptBridge:
    def __init__(self, cdp_url: str = "http://127.0.0.1:9222"):
        self.cdp_url = cdp_url

    async def send_prompt(self, text: str, image_bytes: bytes | None = None) -> None:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(self.cdp_url)
            page = self._find_chatgpt_page(browser)
            if image_bytes is not None:
                file_input = None
                for selector in (
                    "#upload-files",
                    "#upload-photos-input",
                    "#upload-photos",
                    "#upload-media-files",
                ):
                    candidate = page.locator(selector)
                    if await candidate.count():
                        file_input = candidate.first
                        break
                if file_input is None:
                    raise RuntimeError("找不到 ChatGPT 的圖片上傳 input")
                await file_input.set_input_files({
                    "name": "homework.jpg",
                    "mimeType": "image/jpeg",
                    "buffer": image_bytes,
                })
            composer = page.locator(COMPOSER_SELECTOR).first
            await composer.click()
            await composer.fill(text)
            await composer.press("Enter")

    @staticmethod
    def _find_chatgpt_page(browser):
        for context in browser.contexts:
            for page in context.pages:
                if any(fragment in page.url for fragment in CHATGPT_URL_FRAGMENTS):
                    return page
        raise RuntimeError(
            "找不到已經開啟的 ChatGPT 分頁；請先在 Chrome 開好 chat.openai.com/chatgpt.com，"
            "並確認 Chrome 是用 --remote-debugging-port 啟動的"
        )
