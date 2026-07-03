import io
import http.client
import json
import unittest
import urllib.error
from unittest.mock import patch
from unittest.mock import Mock

from grading_api.config import Settings
from grading_api.errors import UpstreamError
from grading_api.openai_client import (
    OpenAIResponsesClient,
    _get_first_path,
    _image_upload_response_paths,
    _safe_error_detail,
    _safe_upstream_message,
    build_user_prompt,
    build_reference_parse_prompt,
    extract_output_text,
)
from grading_api.validation import parse_grade_request, parse_reference_parse_request

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


def upload_settings() -> Settings:
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
        image_upload_url="https://api.imgbb.com/1/upload?key=test-key",
        image_upload_field="image",
        image_upload_response_path="data.url",
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
        self.assertIn("Inspect the student image internally", prompt)
        self.assertIn("Do not infer missing or unclear work", prompt)
        self.assertIn("Keep student_answer_summary empty", prompt)

    def test_grade_payload_uses_only_student_answer_image(self):
        request = parse_grade_request(valid_payload(), max_image_bytes=1024)
        client = OpenAIResponsesClient(settings())

        body = client._build_chat_payload(request)
        content = body["messages"][1]["content"]
        image_urls = [item["image_url"] for item in content if item["type"] == "image_url"]

        self.assertEqual(len(image_urls), 1)
        self.assertIn("teacher has already confirmed", content[0]["text"])
        self.assertIn("suggested_score, max_score", content[0]["text"])
        self.assertEqual(body["max_tokens"], 450)

    def test_reference_parse_payload_uses_one_reference_image(self):
        payload = valid_payload()
        request = parse_reference_parse_request({"image": payload["image"]}, max_image_bytes=1024)
        client = OpenAIResponsesClient(settings())

        body = client._build_reference_chat_payload(request)
        content = body["messages"][0]["content"]
        image_urls = [item["image_url"] for item in content if item["type"] == "image_url"]

        self.assertEqual(len(image_urls), 1)
        self.assertEqual(len(body["messages"]), 1)
        self.assertEqual(body["max_tokens"], 500)
        self.assertIn("Read this teacher reference image", content[0]["text"])
        self.assertNotIn("math grading task", content[0]["text"])
        self.assertIn("standard_answer, grading_rules", build_reference_parse_prompt(request))

    def test_grade_uses_chat_completions_directly_for_image_url_flow(self):
        request = parse_grade_request(valid_payload(), max_image_bytes=1024)
        client = OpenAIResponsesClient(settings())
        chat_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "suggested_score": 6,
                                "max_score": 6,
                                "confidence": 0.9,
                                "needs_review": False,
                                "review_reason": "",
                                "deduction_points": [],
                                "student_answer_summary": "Correct answer.",
                                "uncertain_factors": [],
                            }
                        )
                    }
                }
            ]
        }

        with patch.object(
            client,
            "_post_json",
            return_value=chat_response,
        ) as post_json:
            result = client.grade(request)

        self.assertEqual(result["suggested_score"], 6)
        self.assertEqual(post_json.call_count, 1)
        self.assertTrue(post_json.call_args.args[0].endswith("/chat/completions"))

    def test_parse_reference_uses_chat_completions_directly_for_image_url_flow(self):
        request = parse_reference_parse_request({"image": valid_payload()["image"]}, max_image_bytes=1024)
        client = OpenAIResponsesClient(settings())
        chat_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "standard_answer": "x = 2",
                                "grading_rules": "Equation 2 points; final answer 4 points.",
                                "deduction_rules": "Blank answer gets 0.",
                                "max_score": 6,
                                "confidence": 0.9,
                                "needs_review": False,
                                "review_reason": "",
                                "uncertain_factors": [],
                            }
                        )
                    }
                }
            ]
        }

        with patch.object(client, "_post_json", return_value=chat_response) as post_json:
            result = client.parse_reference(request)

        self.assertEqual(result["standard_answer"], "x = 2")
        self.assertEqual(post_json.call_count, 1)
        self.assertTrue(post_json.call_args.args[0].endswith("/chat/completions"))

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

    def test_model_post_uses_curl_when_available(self):
        client = OpenAIResponsesClient(settings())

        with patch("grading_api.openai_client._find_curl_executable", return_value="curl.exe"), patch.object(
            client, "_post_json_with_curl", return_value='{"ok": true}'
        ) as curl_post, patch.object(client, "_post_json_with_urllib") as urllib_post:
            result = client._post_json("https://api.openai.com/v1/chat/completions", {"model": "fake-model"})

        self.assertEqual(result, {"ok": True})
        self.assertEqual(curl_post.call_count, 1)
        urllib_post.assert_not_called()

    def test_model_post_retries_curl_before_success(self):
        client = OpenAIResponsesClient(settings())

        with patch("grading_api.openai_client._find_curl_executable", return_value="curl.exe"), patch(
            "grading_api.openai_client.time.sleep"
        ) as sleep, patch.object(
            client,
            "_post_json_with_curl",
            side_effect=[UpstreamError("Could not reach the model API."), '{"ok": true}'],
        ) as curl_post:
            result = client._post_json("https://api.openai.com/v1/chat/completions", {"model": "fake-model"})

        self.assertEqual(result, {"ok": True})
        self.assertEqual(curl_post.call_count, 2)
        sleep.assert_called_once()

    def test_model_post_falls_back_to_urllib_when_curl_is_missing(self):
        client = OpenAIResponsesClient(settings())

        with patch("grading_api.openai_client._find_curl_executable", return_value=None), patch.object(
            client, "_post_json_with_urllib", return_value='{"ok": true}'
        ) as urllib_post:
            result = client._post_json("https://api.openai.com/v1/chat/completions", {"model": "fake-model"})

        self.assertEqual(result, {"ok": True})
        self.assertEqual(urllib_post.call_count, 1)

    def test_model_post_accepts_single_sse_json_chunk(self):
        client = OpenAIResponsesClient(settings())

        with patch("grading_api.openai_client._find_curl_executable", return_value="curl.exe"), patch.object(
            client, "_post_json_with_curl", return_value='data: {"ok": true}\n\ndata: [DONE]\n'
        ):
            result = client._post_json("https://api.openai.com/v1/chat/completions", {"model": "fake-model"})

        self.assertEqual(result, {"ok": True})

    def test_imgbb_response_paths_fall_back_to_model_readable_variants(self):
        paths = _image_upload_response_paths(
            upload_url="https://api.imgbb.com/1/upload?key=test-key",
            configured_path="data.medium.url",
        )
        payload = {
            "data": {
                "thumb": {"url": "https://i.ibb.co/thumb/test.png"},
                "url": "https://i.ibb.co/original/test.png",
            }
        }

        self.assertEqual(
            paths,
            ("data.medium.url", "data.thumb.url", "data.display_url", "data.url"),
        )
        self.assertEqual(_get_first_path(payload, paths), "https://i.ibb.co/thumb/test.png")

    def test_image_upload_uses_curl_when_available(self):
        client = OpenAIResponsesClient(upload_settings())
        response_body = json.dumps({"data": {"url": "https://i.ibb.co/original/test.png"}})

        with patch("grading_api.openai_client._find_curl_executable", return_value="curl.exe"), patch.object(
            client, "_upload_image_with_curl", return_value=response_body
        ) as curl_upload, patch.object(client, "_upload_image_with_urllib") as urllib_upload:
            url = client._upload_image_for_url(valid_payload()["image"])

        self.assertEqual(url, "https://i.ibb.co/original/test.png")
        self.assertEqual(curl_upload.call_count, 1)
        urllib_upload.assert_not_called()

    def test_image_upload_retries_curl_before_success(self):
        client = OpenAIResponsesClient(upload_settings())
        response_body = json.dumps({"data": {"url": "https://i.ibb.co/original/test.png"}})

        with patch("grading_api.openai_client._find_curl_executable", return_value="curl.exe"), patch(
            "grading_api.openai_client.time.sleep"
        ) as sleep, patch.object(
            client,
            "_upload_image_with_curl",
            side_effect=[UpstreamError("Image URL service is unavailable."), response_body],
        ) as curl_upload:
            url = client._upload_image_for_url(valid_payload()["image"])

        self.assertEqual(url, "https://i.ibb.co/original/test.png")
        self.assertEqual(curl_upload.call_count, 2)
        sleep.assert_called_once()

    def test_image_upload_falls_back_to_urllib_when_curl_is_missing(self):
        client = OpenAIResponsesClient(upload_settings())
        response_body = json.dumps({"data": {"url": "https://i.ibb.co/original/test.png"}})

        with patch("grading_api.openai_client._find_curl_executable", return_value=None), patch.object(
            client, "_upload_image_with_urllib", return_value=response_body
        ) as urllib_upload:
            url = client._upload_image_for_url(valid_payload()["image"])

        self.assertEqual(url, "https://i.ibb.co/original/test.png")
        self.assertEqual(urllib_upload.call_count, 1)

    def test_remote_disconnect_is_reported_as_upstream_error(self):
        client = OpenAIResponsesClient(settings())

        with patch("grading_api.openai_client._find_curl_executable", return_value=None), patch(
            "grading_api.openai_client.time.sleep"
        ), patch(
            "grading_api.openai_client.urllib.request.urlopen",
            side_effect=http.client.RemoteDisconnected("closed"),
        ):
            with self.assertRaises(UpstreamError) as context:
                client._post_json("https://api.openai.com/v1/chat/completions", {"model": "fake-model"})

        self.assertEqual(context.exception.error_code, "upstream_error")
        self.assertEqual(context.exception.details["reason"], "RemoteDisconnected")

    def test_remote_disconnect_retries_before_success(self):
        client = OpenAIResponsesClient(settings())
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        response.read.return_value = b'{"ok": true}'

        with patch("grading_api.openai_client._find_curl_executable", return_value=None), patch(
            "grading_api.openai_client.time.sleep"
        ), patch(
            "grading_api.openai_client.urllib.request.urlopen",
            side_effect=[http.client.RemoteDisconnected("closed"), response],
        ) as urlopen:
            result = client._post_json("https://api.openai.com/v1/chat/completions", {"model": "fake-model"})

        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 2)

    def test_http_error_detail_does_not_expose_provider_message(self):
        body = json.dumps(
            {
                "error": {
                    "type": "invalid_request_error",
                    "code": "invalid_api_key",
                    "message": "Incorrect API key provided: secret-token",
                }
            }
        ).encode("utf-8")
        error = urllib.error.HTTPError(
            url="https://api.openai.com/v1/chat/completions",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=io.BytesIO(body),
        )

        detail = _safe_error_detail(error)

        self.assertEqual(detail["status"], 401)
        self.assertEqual(detail["code"], "invalid_api_key")
        self.assertNotIn("message", detail)
        self.assertNotIn("secret-token", json.dumps(detail))
        self.assertEqual(
            _safe_upstream_message(detail),
            "Model API credentials are invalid or not authorized.",
        )


if __name__ == "__main__":
    unittest.main()
