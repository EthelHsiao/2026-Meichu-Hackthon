import unittest

from main import Companion


class HomeworkTriggerTests(unittest.TestCase):
    def test_trigger_guard_accepts_first_event_and_rejects_inflight_duplicate(self):
        class InFlightTask:
            def done(self):
                return False

        companion = object.__new__(Companion)
        companion._homework_task = InFlightTask()
        companion._last_homework_trigger = 100.0

        self.assertFalse(companion._accept_homework_trigger(now=100.1))

    def test_trigger_guard_accepts_after_cooldown_when_no_flow_is_running(self):
        companion = object.__new__(Companion)
        companion._homework_task = None
        companion._last_homework_trigger = 100.0

        self.assertTrue(companion._accept_homework_trigger(now=103.1))


if __name__ == "__main__":
    unittest.main()
