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
        response = {
            "app": "code", "activity": "在 main.py 除錯", "evidence": [],
            "error": {"kind": "runtime", "code": None, "message": "KeyError: 'response'", "file": None, "line": None},
            "cause": None, "missing_context": [],
        }
        transport = RecordingTransport(response)
        client = MI300Client("http://mi300:8000", "/observations", transport=transport)
        result = client.submit_observation({"observation_id": "o1"}, b"jpeg")
        self.assertEqual(result["error"]["message"], "KeyError: 'response'")
        self.assertEqual(transport.path, "http://mi300:8000/observations")
        self.assertEqual(transport.payload["observation"]["observation_id"], "o1")
        self.assertEqual(transport.payload["image_b64"], "anBlZw==")

    def test_rejects_response_missing_required_fields(self):
        client = MI300Client("http://mi300:8000", "/observations", transport=RecordingTransport({"error": None}))
        with self.assertRaises(ValueError):
            client.submit_observation({"observation_id": "o1"}, b"jpeg")

    def test_default_observation_path_is_restful_v1_route(self):
        client = MI300Client("http://mi300:8000", transport=RecordingTransport({}))
        self.assertEqual(client.path, "/v1/screen-observations")

    def test_reply_extracts_expr_and_text_from_openai_shaped_response(self):
        openai_response = {
            "choices": [{"message": {"content": '{"expr": "worried", "text": "先印出 dict 看看？"}'}}]
        }
        client = MI300Client("http://mi300:8000", transport=RecordingTransport(openai_response))
        result = client.reply([{"role": "user", "content": "怎麼修"}])
        self.assertEqual(result, {"expr": "worried", "text": "先印出 dict 看看？"})

    def test_reply_rejects_response_without_text(self):
        openai_response = {"choices": [{"message": {"content": '{"expr": "worried"}'}}]}
        client = MI300Client("http://mi300:8000", transport=RecordingTransport(openai_response))
        with self.assertRaises(ValueError):
            client.reply([{"role": "user", "content": "怎麼修"}])

    def test_analyze_homework_posts_image_and_transcript(self):
        transport = RecordingTransport(
            {"analysis": "第一題...", "reassurance": {"expr": "neutral", "text": "辛苦了"}, "chatgpt_prompt": "..."}
        )
        client = MI300Client("http://mi300:8000", transport=transport)
        result = client.analyze_homework(b"jpeg", "這題好難")
        self.assertEqual(transport.path, "http://mi300:8000/v1/homework-analyses")
        self.assertEqual(transport.payload["transcript"], "這題好難")
        self.assertEqual(result["reassurance"]["text"], "辛苦了")

    def test_analyze_homework_rejects_incomplete_response(self):
        client = MI300Client("http://mi300:8000", transport=RecordingTransport({"analysis": "x"}))
        with self.assertRaises(ValueError):
            client.analyze_homework(b"jpeg")


if __name__ == "__main__":
    unittest.main()
