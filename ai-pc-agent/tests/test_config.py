import unittest

import config


class ConfigTests(unittest.TestCase):
    def test_default_timing_matches_work_tracker_policy(self):
        self.assertEqual(config.LOCAL_POLL_SECONDS, 10)
        self.assertEqual(config.SCREENSHOT_SECONDS, 30)
        self.assertEqual(config.MIN_VLM_SECONDS, 60)
        self.assertEqual(config.IDLE_THRESHOLD_SECONDS, 60)


if __name__ == "__main__":
    unittest.main()
