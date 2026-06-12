# API Contract Draft

This file records early API boundaries. Feature branches may update it as the grading API and UI are implemented.

## Health

`GET /api/health`

Response:

```json
{
  "ok": true,
  "service": "exam-grading-assistant",
  "hasOpenAiKey": true,
  "gradingApiBaseUrl": "http://127.0.0.1:8765"
}
```

## Browser Grading Proxy

`POST /api/grade-answer`

Implemented by the Node web server. It accepts the same payload shape as the Python grading API and forwards it to `GRADING_API_URL` or `GRADING_API_HOST:GRADING_API_PORT`.

Request:

```json
{
  "question_id": "local-question-001",
  "max_score": 6,
  "standard_answer": "Teacher-provided standard answer.",
  "standard_answer_image": null,
  "grading_rules": "Teacher-provided scoring rules.",
  "grading_rules_image": null,
  "deduction_rules": "Teacher-provided deduction rules.",
  "allow_equivalent_answers": true,
  "score_by_steps": true,
  "score_precision": "0.5",
  "rule_version": "v1",
  "image": "data:image/png;base64,...",
  "mode": "suggest_only"
}
```

Response:

```json
{
  "suggested_score": 4,
  "max_score": 6,
  "confidence": 0.82,
  "needs_review": true,
  "review_reason": "Confidence is below 0.90; teacher review is recommended.",
  "deduction_points": [
    "Calculation error in the second step."
  ],
  "student_answer_summary": "Short model-visible answer summary.",
  "uncertain_factors": [],
  "model": "gpt-4.1",
  "prompt_version": "grading-api-v1",
  "rule_version": "v1",
  "question_id": "local-question-001"
}
```

`standard_answer` and `grading_rules` may be empty strings when the matching `standard_answer_image` or `grading_rules_image` data URI is provided. Reference images must be PNG, JPEG, or WebP data URIs and are treated as teacher-provided grading material, not student work.

## Python Grading API

`POST /api/grade`

This endpoint is served by `python -m grading_api.server`. Browser code should normally call `/api/grade-answer` on the Node server instead, so local API tokens and cross-port details stay out of frontend code.
