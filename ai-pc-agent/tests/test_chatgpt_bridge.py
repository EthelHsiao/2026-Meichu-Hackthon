import asyncio
import sys
import types
import unittest
from unittest.mock import patch

from chatgpt_bridge import ChatGptBridge


class FakeLocator:
    def __init__(self, calls):
        self.calls = calls

    @property
    def first(self):
        return self

    async def count(self):
        return 1

    async def set_input_files(self, payload):
        self.calls.append(("set_input_files", payload))

    async def click(self):
        self.calls.append(("click",))

    async def fill(self, text):
        self.calls.append(("fill", text))

    async def press(self, key):
        self.calls.append(("press", key))


class FakePage:
    url = "https://chatgpt.com/c/test"

    def __init__(self):
        self.calls = []

    def locator(self, selector):
        self.calls.append(("locator", selector))
        return FakeLocator(self.calls)


class FakeBrowser:
    def __init__(self, page):
        self.contexts = [types.SimpleNamespace(pages=[page])]


class FakePlaywrightContext:
    def __init__(self, browser):
        self.browser = browser
        self.chromium = types.SimpleNamespace(connect_over_cdp=self.connect_over_cdp)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def connect_over_cdp(self, url):
        return self.browser


class ChatGptBridgeTests(unittest.TestCase):
    def test_send_prompt_attaches_image_before_submitting_text(self):
        page = FakePage()
        browser = FakeBrowser(page)
        playwright_module = types.ModuleType("playwright.async_api")
        playwright_module.async_playwright = lambda: FakePlaywrightContext(browser)

        with patch.dict(sys.modules, {
            "playwright": types.ModuleType("playwright"),
            "playwright.async_api": playwright_module,
        }):
            asyncio.run(ChatGptBridge().send_prompt("請幫我看這題", b"jpeg-bytes"))

        self.assertEqual(page.calls[0], ("locator", "#upload-files"))
        self.assertEqual(page.calls[1], ("set_input_files", {
            "name": "homework.jpg",
            "mimeType": "image/jpeg",
            "buffer": b"jpeg-bytes",
        }))
        self.assertIn(("fill", "請幫我看這題"), page.calls)
        self.assertIn(("press", "Enter"), page.calls)


if __name__ == "__main__":
    unittest.main()
