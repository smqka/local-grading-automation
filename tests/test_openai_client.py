import json
import unittest

from grading_api.config import Settings
from grading_api.openai_client import OpenAIResponsesClient, build_user_prompt, extract_output_text
from grading_api.validation import parse_grade_request

from tests.test_grading_service import valid_payload


def settings() -> Settings:
    return Settings(
        host="127.0.0.1",
        port=0,
        openai_api_key="test-key",
        openai_base_url="https://api.openai.com/v1",
        openai_model="fake-model",
        prompt_version="test-prompt",
        request_timeout_seconds=1,
        max_image_bytes=1024,
        api_token=None,
        allowed_origins=("http://localhost:5173",),
    )


class OpenAIClientHelpersTest(unittest.TestCase):
    def test_extract_output_text_from_response_output(self):
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "{\"suggested_score\": 4}"},
                    ],
                }
            ]
        }

        self.assertEqual(extract_output_text(payload), "{\"suggested_score\": 4}")

    def test_extract_output_text_prefers_direct_field(self):
        self.assertEqual(extract_output_text({"output_text": "hello", "output": []}), "hello")

    def test_prompt_contains_teacher_rubric(self):
        request = parse_grade_request(valid_payload(), max_image_bytes=1024)
        prompt = build_user_prompt(request)

        self.assertIn("x = 2", prompt)
        self.assertIn("Equation 2 points", prompt)
        self.assertIn("Max score: 6.0", prompt)

    def test_payload_includes_reference_images(self):
        payload = valid_payload()
        payload["standard_answer"] = ""
        payload["grading_rules"] = ""
        payload["standard_answer_image"] = payload["image"]
        payload["grading_rules_image"] = payload["image"]
        request = parse_grade_request(payload, max_image_bytes=1024)
        client = OpenAIResponsesClient(settings())

        body = client._build_payload(request)
        content = body["input"][0]["content"]
        image_urls = [item["image_url"] for item in content if item["type"] == "input_image"]

        self.assertEqual(len(image_urls), 3)
        self.assertIn("Standard answer image provided: yes", content[0]["text"])
        self.assertIn("Grading rules image provided: yes", content[0]["text"])

    def test_schema_text_is_valid_json_when_embedded(self):
        response = extract_output_text(
            {
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps({"suggested_score": 3}, ensure_ascii=False),
                            }
                        ]
                    }
                ]
            }
        )

        self.assertEqual(json.loads(response)["suggested_score"], 3)


if __name__ == "__main__":
    unittest.main()
