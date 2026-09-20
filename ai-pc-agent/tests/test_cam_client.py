import unittest
from unittest.mock import patch

import cam_client


class SnapshotTransportTests(unittest.TestCase):
    def test_snapshot_retries_when_stream_connection_is_releasing(self):
        class Response:
            content = b"jpeg"

            def raise_for_status(self):
                return None

        class Transport:
            calls = 0

            def get(self, url, timeout):
                self.calls += 1
                if self.calls == 1:
                    raise TimeoutError("stream still connected")
                return Response()

        transport = Transport()
        with patch.object(cam_client.time, "sleep") as sleep:
            result = cam_client.capture_snapshot(
                transport=transport, base_url="http://camera", attempts=2, retry_delay=0.2
            )

        self.assertEqual(result, b"jpeg")
        self.assertEqual(transport.calls, 2)
        sleep.assert_called_once_with(0.2)


if __name__ == "__main__":
    unittest.main()
