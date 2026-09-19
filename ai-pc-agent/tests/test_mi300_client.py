import unittest

from mi300_client import MI300Client


class RecordingTransport:
    def __init__(self, response):
        self.response = response
        self.path = None
        self.payload = None

    def post(self, url, *, json, timeout):
        self.path = url
        self.payload = json
        return self.response


class ClientTests(unittest.TestCase):
    def test_posts_observation_and_image_to_configured_route(self):
        transport = RecordingTransport({"memory_id": "m1", "activity": "writing", "confidence": 0.9, "evidence": []})
        client = MI300Client("http://mi300:8000", "/observations", transport=transport)
        result = client.submit_observation({"observation_id": "o1"}, b"jpeg")
        self.assertEqual(result["memory_id"], "m1")
        self.assertEqual(transport.path, "http://mi300:8000/observations")
        self.assertEqual(transport.payload["observation"]["observation_id"], "o1")
        self.assertEqual(transport.payload["image_b64"], "anBlZw==")


if __name__ == "__main__":
    unittest.main()
