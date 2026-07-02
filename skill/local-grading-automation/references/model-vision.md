# Model Vision Integration

Use this file when changing model calls, image upload behavior, or prompts.

## Preferred Input Shape

Prefer one current student-answer image plus teacher-confirmed text rules:

- `standard_answer`
- `grading_rules`
- `deduction_rules`
- `max_score`
- `score_precision`
- current cropped answer image

Avoid multi-image prompts unless the target gateway is known to support them reliably.

## Gateway Compatibility

OpenAI-compatible gateways vary:

- Some accept `data:image/...;base64,...` in `image_url`.
- Some require a public HTTPS image URL.
- Some reject vision input even if text chat works.

When base64 fails, use a public URL only after explaining privacy tradeoffs. Prefer self-owned object storage with short-lived URLs for production-like use.

## Prompt Rules

The model should:

- Score only visible work.
- Avoid inferring missing student work from the rubric.
- Return concise structured JSON.
- Lower confidence for unclear handwriting, cropped content, mixed questions, or ambiguous steps.
- Keep suggested score within `0` and `max_score`.

## Output Validation

Always validate model output before using it:

- Coerce score to the configured precision.
- Force review on invalid score, out-of-range score, malformed JSON, or low confidence.
- Never let malformed output trigger auto-clicking.
