import unittest

from detector import ChangeDetector, normalize_title


def state(app, title, idle, phash, *, enrichments=None):
    return {
        "foreground": {"app": app, "window_title": title, "workspace": None},
        "system": {"running_apps": [app], "idle_seconds": idle},
        "screen": {"perceptual_hash": phash},
        "enrichments": enrichments or {"git": None, "vscode": None, "browser": None, "terminal": None},
    }


class DetectorTests(unittest.TestCase):
    def test_trivial_title_suffix_change_does_not_trigger(self):
        detector = ChangeDetector(min_vlm_seconds=60)
        old = state("code", "main.py — VS Code", idle=2, phash="aaaa")
        new = state("code", "main.py — VS Code • 1", idle=2, phash="aaaa")
        self.assertFalse(detector.should_submit(old, new, now=100))

    def test_foreground_change_triggers_and_minimum_interval_is_respected(self):
        detector = ChangeDetector(min_vlm_seconds=60)
        old = state("code", "main.py", idle=2, phash="aaaa")
        new = state("chrome", "LeetCode", idle=2, phash="bbbb")
        self.assertTrue(detector.should_submit(old, new, now=100))
        detector.mark_submitted(new, now=100)
        self.assertFalse(detector.should_submit(new, state("chrome", "LeetCode", 2, "cccc"), now=130))
        self.assertTrue(detector.should_submit(new, state("chrome", "LeetCode", 2, "cccc"), now=161))

    def test_idle_to_active_is_a_meaningful_change(self):
        detector = ChangeDetector(min_vlm_seconds=60, idle_threshold=60)
        old = state("chrome", "LeetCode", idle=90, phash="aaaa")
        new = state("chrome", "LeetCode", idle=2, phash="aaaa")
        self.assertTrue(detector.should_submit(old, new, now=100))

    def test_title_normalization(self):
        self.assertEqual(normalize_title("main.py — VS Code • 1"), "main.py")


if __name__ == "__main__":
    unittest.main()
