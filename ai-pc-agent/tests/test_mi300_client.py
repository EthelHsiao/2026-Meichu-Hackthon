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
        transport = RecordingTransport({"text": "在 main.py 遇到 KeyError", "error": "KeyError: 'response'"})
        client = MI300Client("http://mi300:8000", "/observations", transport=transport)
        result = client.submit_observation({"observation_id": "o1"}, b"jpeg")
        self.assertEqual(result["error"], "KeyError: 'response'")
        self.assertEqual(transport.path, "http://mi300:8000/observations")
        self.assertEqual(transport.payload["observation"]["observation_id"], "o1")
        self.assertEqual(transport.payload["image_b64"], "anBlZw==")

    def test_rejects_response_without_text(self):
        client = MI300Client("http://mi300:8000", "/observations", transport=RecordingTransport({"error": None}))
        with self.assertRaises(ValueError):
            client.submit_observation({"observation_id": "o1"}, b"jpeg")


if __name__ == "__main__":
    unittest.main()
