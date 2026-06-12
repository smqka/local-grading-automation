# API Contract Draft

This file records early API boundaries. Feature branches may update it as the grading API and UI are implemented.

## Health

`GET /api/health`

Response:

```json
{
  "ok": true,
  "service": "exam-grading-assistant",
  "hasOpenAiKey": true
}
```

## Future Grading Endpoint

`POST /api/grade-answer`

Status: planned for `feature/grading-api`.

Request:

```json
{
  "questionId": "local-question-001",
  "maxScore": 6,
  "standardAnswer": "Teacher-provided standard answer.",
  "rubric": "Teacher-provided scoring rules.",
  "image": "data:image/png;base64,...",
  "mode": "suggest_only"
}
```

Response:

```json
{
  "suggestedScore": 4,
  "maxScore": 6,
  "confidence": 0.82,
  "reviewRequired": true,
  "reasons": [
    "Calculation error in the second step."
  ],
  "detectedAnswerSummary": "Short model-visible answer summary.",
  "warnings": []
}
```
