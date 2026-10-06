import os
import tempfile
import time
import unittest
from pathlib import Path

from screenshot import ScreenshotCapture


class ScreenshotRetentionTests(unittest.TestCase):
    """prune() 是唯一會刪使用者畫面歷史的地方，所以邊界要測清楚。
    capture() 本身需要 mss/PIL 和真的螢幕，這裡只測保留規則。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _shot(self, name: str, age_minutes: float) -> Path:
        path = self.directory / name
        path.write_bytes(b"fake-jpeg")
        stamp = time.time() - age_minutes * 60
        os.utime(path, (stamp, stamp))
        return path

    def test_removes_only_files_older_than_retention(self):
        old = self._shot("old.jpg", age_minutes=30)
        fresh = self._shot("fresh.jpg", age_minutes=1)
        capture = ScreenshotCapture(directory=str(self.directory), retention_minutes=10)

        self.assertEqual(capture.prune(), 1)
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())

    def test_zero_retention_clears_everything_already_on_disk(self):
        previous = self._shot("previous.jpg", age_minutes=0.5)
        capture = ScreenshotCapture(directory=str(self.directory), retention_minutes=0)

        self.assertEqual(capture.prune(), 1)
        self.assertFalse(previous.exists())

    def test_negative_retention_disables_pruning(self):
        ancient = self._shot("ancient.jpg", age_minutes=10_000)
        capture = ScreenshotCapture(directory=str(self.directory), retention_minutes=-1)

        self.assertEqual(capture.prune(), 0)
        self.assertTrue(ancient.exists())

    def test_leaves_non_screenshot_files_alone(self):
        note = self.directory / "README.txt"
        note.write_text("not a screenshot")
        stamp = time.time() - 10_000
        os.utime(note, (stamp, stamp))
        capture = ScreenshotCapture(directory=str(self.directory), retention_minutes=1)

        self.assertEqual(capture.prune(), 0)
        self.assertTrue(note.exists())

    def test_missing_directory_is_not_an_error(self):
        capture = ScreenshotCapture(directory=str(self.directory / "nope"), retention_minutes=1)

        self.assertEqual(capture.prune(), 0)


if __name__ == "__main__":
    unittest.main()
