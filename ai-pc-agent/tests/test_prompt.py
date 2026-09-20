import unittest

from prompt import build_messages
from state import ContextState


class BuildMessagesTests(unittest.TestCase):
    def test_system_prompt_constrains_output_shape(self):
        messages = build_messages(ContextState(), [], [], "")
        system = messages[0]["content"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("expr", system)
        self.assertIn("text", system)

    def test_system_prompt_uses_cute_but_clear_companion_style(self):
        system = build_messages(ContextState(), [], [], "")[0]["content"]
        self.assertIn("可愛", system)
        self.assertIn("不要過度撒嬌", system)
        self.assertIn("技術回答仍要清楚", system)

    def test_system_prompt_encourages_every_attempt(self):
        system = build_messages(ContextState(), [], [], "")[0]["content"]
        self.assertIn("每一次嘗試都給予正向鼓勵", system)
        self.assertIn("小進展或遇到 bug", system)

    def test_system_prompt_requires_contextual_specific_encouragement(self):
        system = build_messages(ContextState(), [], [], "")[0]["content"]
        self.assertIn("實際使用【使用者檔案】、【最近狀態】和【相關記憶】", system)
        self.assertIn("鼓勵或安慰時盡量具體點出那件事", system)
        self.assertIn("不要只給空泛的「加油」", system)

    def test_system_prompt_forbids_canned_or_invented_context(self):
        system = build_messages(ContextState(), [], [], "")[0]["content"]
        self.assertIn("至少包含一個來自 context 的具體細節", system)
        self.assertIn("不要套用固定句型", system)
        self.assertIn("不要自行杜撰", system)

    def test_user_content_includes_all_sections(self):
        state = ContextState(app="code", activity="在 main.py 除錯", error="KeyError: 'response'")
        messages = build_messages(
            state, ["[09:20] 在 main.py 遇到 KeyError"], ["之前也遇過同一個 KeyError"],
            "這個到底怎麼修", facts=["在做 ESP32 桌寵專案"], touch={"kind": "squeeze", "strength": 0.8},
        )
        user = messages[1]["content"]
        self.assertIn("在做 ESP32 桌寵專案", user)
        self.assertIn("main.py 除錯", user)
        self.assertIn("KeyError", user)
        self.assertIn("這個到底怎麼修", user)
        self.assertIn("squeeze", user)

    def test_empty_user_text_marks_proactive_turn(self):
        messages = build_messages(ContextState(), [], [], "")
        self.assertIn("主動發話", messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
