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
