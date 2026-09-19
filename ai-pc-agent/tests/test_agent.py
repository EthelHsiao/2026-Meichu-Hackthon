import unittest

from agent import BoundedRetryQueue


class AgentTests(unittest.TestCase):
    def test_failed_delivery_is_bounded_and_does_not_raise(self):
        queue = BoundedRetryQueue(max_items=2)
        queue.put(({"observation_id": "1"}, b"1"))
        queue.put(({"observation_id": "2"}, b"2"))
        queue.put(({"observation_id": "3"}, b"3"))
        self.assertEqual(queue.size(), 2)
        self.assertEqual(queue.get()[0]["observation_id"], "2")


if __name__ == "__main__":
    unittest.main()
