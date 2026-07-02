import unittest

from grading_api.config import Settings
from grading_api.errors import BadRequestError
from grading_api.models import GradeRequest, ReferenceParseRequest
from grading_api.service import GradingService
from grading_api.validation import (
    parse_grade_request,
    parse_reference_parse_request,
    validate_model_result,
    validate_reference_parse_result,
)


PNG_1X1 = "data:image/png;base64,iVBORw0KGgo="


class FakeClient:
    model_name = "fake-model"

    def __init__(self, response):
        self.response = response
        self.last_request = None

    def grade(self, request: GradeRequest):
        self.last_request = request
        return self.response

    def parse_reference(self, request: ReferenceParseRequest):
        self.last_request = request
        return self.response


def settings() -> Settings:
    return Settings(
        host="127.0.0.1",
        port=0,
        openai_api_key=None,
        openai_base_url="https://api.openai.com/v1",
        openai_model="fake-model",
        prompt_version="test-prompt",
        request_timeout_seconds=1,
        max_image_bytes=1024,
        api_token=None,
        allowed_origins=("http://localhost:5173",),
    )


def valid_payload():
    return {
        "image": PNG_1X1,
        "max_score": 6,
        "standard_answer": "x = 2",
        "grading_rules": "Equation 2 points, simplification 2 points, final answer 2 points.",
        "deduction_rules": "Blank answer gets 0.",
        "allow_equivalent_answers": True,
        "score_by_steps": True,
        "score_precision": "0.5",
        "question_id": "q1",
        "rule_version": "v1",
    }


class ParseGradeRequestTest(unittest.TestCase):
    def test_accepts_data_uri_image(self):
        request = parse_grade_request(valid_payload(), max_image_bytes=1024)

        self.assertEqual(request.image.mime_type, "image/png")
        self.assertEqual(request.max_score, 6)
        self.assertEqual(request.score_precision, "0.5")

    def test_rejects_reference_images_instead_of_confirmed_text(self):
        payload = valid_payload()
        payload["standard_answer"] = ""
        payload["grading_rules"] = ""
        payload["standard_answer_image"] = PNG_1X1
        payload["grading_rules_image"] = PNG_1X1

        with self.assertRaises(BadRequestError):
            parse_grade_request(payload, max_image_bytes=1024)

    def test_accepts_reference_image_for_parse_step(self):
        request = parse_reference_parse_request({"image": PNG_1X1}, max_image_bytes=1024)

        self.assertEqual(request.image.mime_type, "image/png")

    def test_rejects_missing_rubric(self):
        payload = valid_payload()
        payload["grading_rules"] = ""

        with self.assertRaises(BadRequestError):
            parse_grade_request(payload, max_image_bytes=1024)

    def test_rejects_missing_standard_answer_text_and_image(self):
        payload = valid_payload()
        payload["standard_answer"] = ""

        with self.assertRaises(BadRequestError):
            parse_grade_request(payload, max_image_bytes=1024)

    def test_rejects_oversized_image(self):
        with self.assertRaises(BadRequestError):
            parse_grade_request(valid_payload(), max_image_bytes=1)


class ValidateModelResultTest(unittest.TestCase):
    def test_valid_result_passes_through(self):
        request = parse_grade_request(valid_payload(), max_image_bytes=1024)
        result = validate_model_result(
            {
                "suggested_score": 5.5,
                "max_score": 6,
                "confidence": 0.95,
                "needs_review": False,
                "review_reason": "",
                "deduction_points": ["Minor calculation slip."],
                "student_answer_summary": "Student solved most steps.",
                "uncertain_factors": [],
            },
            request,
        )

        self.assertEqual(result.suggested_score, 5.5)
        self.assertFalse(result.needs_review)

    def test_out_of_range_score_forces_review(self):
        request = parse_grade_request(valid_payload(), max_image_bytes=1024)
        result = validate_model_result(
            {
                "suggested_score": 8,
                "max_score": 6,
                "confidence": 0.96,
                "needs_review": False,
                "review_reason": "",
                "deduction_points": [],
                "student_answer_summary": "",
                "uncertain_factors": [],
            },
            request,
        )

        self.assertIsNone(result.suggested_score)
        self.assertTrue(result.needs_review)
        self.assertIn("between 0 and max_score", result.review_reason)

    def test_low_confidence_forces_review(self):
        request = parse_grade_request(valid_payload(), max_image_bytes=1024)
        result = validate_model_result(
            {
                "suggested_score": 4,
                "max_score": 6,
                "confidence": 0.65,
                "needs_review": False,
                "review_reason": "",
                "deduction_points": [],
                "student_answer_summary": "",
                "uncertain_factors": ["handwriting unclear"],
            },
            request,
        )

        self.assertTrue(result.needs_review)
        self.assertIn("below 0.70", result.review_reason)


class GradingServiceTest(unittest.TestCase):
    def test_grade_payload_returns_api_response(self):
        fake = FakeClient(
            {
                "suggested_score": 5,
                "max_score": 6,
                "confidence": 0.92,
                "needs_review": False,
                "review_reason": "",
                "deduction_points": ["Missing final simplification."],
                "student_answer_summary": "Equation is mostly correct.",
                "uncertain_factors": [],
            }
        )
        service = GradingService(settings(), model_client=fake)

        response = service.grade_payload(valid_payload())

        self.assertEqual(response.suggested_score, 5)
        self.assertEqual(response.model, "fake-model")
        self.assertEqual(response.prompt_version, "test-prompt")
        self.assertEqual(response.question_id, "q1")

    def test_parse_reference_payload_returns_editable_text_rules(self):
        fake = FakeClient(
            {
                "standard_answer": "x = 2",
                "grading_rules": "Equation 2 points; steps 2 points; final answer 2 points.",
                "deduction_rules": "Blank answer gets 0.",
                "max_score": 6,
                "confidence": 0.91,
                "needs_review": False,
                "review_reason": "",
                "uncertain_factors": [],
            }
        )
        service = GradingService(settings(), model_client=fake)

        response = service.parse_reference_payload({"image": PNG_1X1, "question_id": "q1"})

        self.assertEqual(response.standard_answer, "x = 2")
        self.assertEqual(response.max_score, 6)
        self.assertEqual(response.question_id, "q1")

    def test_reference_parse_result_coerces_nested_text(self):
        result = validate_reference_parse_result(
            {
                "standard_answer": {"22(1)": "-3, 9", "22(2)": "D(2,-4)"},
                "grading_rules": [
                    {"part": "22(1)", "score": "2 points"},
                    {"part": "22(2)", "score": "4 points"},
                ],
                "deduction_rules": {"blank": "0 points"},
                "max_score": 6,
                "confidence": 0.9,
                "needs_review": False,
                "review_reason": "",
                "uncertain_factors": [],
            }
        )

        self.assertIn("22(1): -3, 9", result.standard_answer)
        self.assertIn("part: 22(1)", result.grading_rules)
        self.assertIn("blank: 0 points", result.deduction_rules)


if __name__ == "__main__":
    unittest.main()
