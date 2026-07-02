# API Contract

This document records the public local API boundaries used by the web UI.

## Web Health

`GET /api/health`

Served by the Node web server.

```json
{
  "ok": true,
  "service": "exam-grading-assistant",
  "hasOpenAiKey": true,
  "gradingApiBaseUrl": "http://127.0.0.1:8765",
  "gradingApi": {
    "ok": true,
    "statusCode": 200,
    "hasOpenAiKey": true
  }
}
```

## Python Health

`GET /health`

Served by the Python grading API.

```json
{
  "status": "ok",
  "has_openai_key": true
}
```

## Grade Answer

Browser route:

`POST /api/grade-answer`

Python route:

`POST /api/grade`

Request:

```json
{
  "question_id": "local-question-001",
  "max_score": 6,
  "standard_answer": "Teacher-provided standard answer.",
  "grading_rules": "Teacher-provided scoring rules.",
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
  "review_reason": "Confidence is below 0.70; teacher review is recommended.",
  "deduction_points": [],
  "student_answer_summary": "",
  "uncertain_factors": [
    "handwriting unclear"
  ],
  "model": "gpt-4.1",
  "prompt_version": "grading-api-v1",
  "rule_version": "v1",
  "question_id": "local-question-001"
}
```

## Parse Reference Image

Browser route:

`POST /api/parse-reference`

Python route:

`POST /api/parse-reference`

This route is optional. The recommended stable workflow is to manually enter and confirm standard-answer text and scoring rules.

## Mouse Position

Browser route:

`GET /api/mouse-position`

Python route:

`GET /api/mouse-position`

Response:

```json
{
  "x": 1200,
  "y": 800,
  "screen": {
    "left": 0,
    "top": 0,
    "width": 2560,
    "height": 1600
  }
}
```

## Click Sequence

Browser route:

`POST /api/click-sequence`

Python route:

`POST /api/click-sequence`

Request:

```json
{
  "points": [
    { "x": 1200, "y": 800 }
  ],
  "delay_ms": 0
}
```

Response:

```json
{
  "ok": true,
  "clicked": [
    { "x": 1200, "y": 800 }
  ],
  "delay_ms": 0
}
```

Mouse endpoints are intended for local use only and should remain bound to `127.0.0.1`.
