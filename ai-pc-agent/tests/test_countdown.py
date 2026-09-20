import unittest

from countdown_html import COUNTDOWN_HTML


class CountdownStageTests(unittest.TestCase):
    def test_countdown_displays_backend_homework_stages(self):
        self.assertIn("homework_stage", COUNTDOWN_HTML)
        self.assertIn("分析逾時", COUNTDOWN_HTML)

    def test_countdown_closes_stream_before_snapshot_phase(self):
        self.assertIn("stopCameraPreview", COUNTDOWN_HTML)
        self.assertIn("camImg.removeAttribute(\"src\")", COUNTDOWN_HTML)


if __name__ == "__main__":
    unittest.main()
