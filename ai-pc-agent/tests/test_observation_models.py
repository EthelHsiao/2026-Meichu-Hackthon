import unittest

from observation_models import build_observation, validate_observation, validate_screen_description


class ObservationModelTests(unittest.TestCase):
    def test_build_observation_supports_arbitrary_app_without_enrichments(self):
        payload = build_observation(
            timestamp="2026-09-19T16:30:00+08:00",
            foreground={"app": "libreoffice", "window_title": "Proposal.odt", "workspace": None},
            system={"running_apps": ["libreoffice"], "idle_seconds": 4},
            screen={"screenshot_path": "/tmp/a.jpg", "image_sha256": "abc", "perceptual_hash": "def"},
        )
        self.assertEqual(payload["foreground"]["app"], "libreoffice")
        self.assertIsNone(payload["enrichments"]["git"])
        self.assertNotIn("keyboard", payload)
        validate_observation(payload)

    def test_observation_has_no_previous_context(self):
        payload = build_observation(
            timestamp="2026-09-19T16:30:00+08:00",
            foreground={"app": "code", "window_title": "main.py"},
            system={"running_apps": [], "idle_seconds": 0},
            screen={},
        )
        self.assertNotIn("previous_context", payload)

    def test_screen_description_needs_all_fields_with_typed_error_and_cause(self):
        base = {"app": "chrome", "activity": "看 YouTube", "evidence": [], "missing_context": []}
        validate_screen_description({**base, "error": None, "cause": None})
        validate_screen_description({
            **base,
            "error": {"kind": "runtime", "code": None, "message": "KeyError: 'response'", "file": None, "line": None},
            "cause": {"explanation": "少寫防呆", "evidence": ["Traceback"]},
        })
        with self.assertRaises(ValueError):
            validate_screen_description({"app": "chrome", "activity": "x"})  # 缺 evidence/error/cause/missing_context
        with self.assertRaises(ValueError):
            validate_screen_description({**base, "error": "KeyError", "cause": None})  # error 不是物件
        with self.assertRaises(ValueError):
            validate_screen_description({**base, "error": None, "cause": "少寫防呆"})  # cause 不是物件


if __name__ == "__main__":
    unittest.main()
