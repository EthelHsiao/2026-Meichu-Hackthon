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

    def test_screen_description_needs_text_and_optional_error(self):
        validate_screen_description({"text": "看 YouTube", "error": None})
        validate_screen_description({"text": "在 main.py 遇到 KeyError", "error": "KeyError: 'response'"})
        with self.assertRaises(ValueError):
            validate_screen_description({"text": "", "error": None})
        with self.assertRaises(ValueError):
            validate_screen_description({"text": "x", "error": 123})


if __name__ == "__main__":
    unittest.main()
