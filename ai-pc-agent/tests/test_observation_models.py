import unittest

from observation_models import build_observation, validate_observation, validate_semantic_memory


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

    def test_invalid_semantic_activity_and_confidence_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_semantic_memory({"activity": "inventing", "confidence": 0.5})
        with self.assertRaises(ValueError):
            validate_semantic_memory({"activity": "coding", "confidence": 2})


if __name__ == "__main__":
    unittest.main()
