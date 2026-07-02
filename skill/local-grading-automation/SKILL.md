---
name: local-grading-automation
description: Build, adapt, debug, and maintain local AI-assisted grading automation tools that use screen capture or uploaded answer images, teacher-confirmed rubrics, vision-model scoring, confidence thresholds, and optional local coordinate clicking. Use when the user wants to create or modify a local grading assistant, automate score-button clicks, configure image-capable model APIs, troubleshoot image_url/base64 gateway issues, or prepare this repository for a specific grading workflow.
---

# Local Grading Automation

## Core Principles

- Keep the tool local-first: bind automation APIs to `127.0.0.1` unless the user explicitly asks otherwise.
- Treat grading output as advice unless the user explicitly enables automation.
- Never click before the current model request returns.
- Invalidate stale model responses when the user pauses, restarts, or continues a new run.
- Prefer one current student-answer image plus teacher-confirmed text rules over multi-image prompts.
- Keep API keys, upload keys, logs, student images, and private grading-system details out of public files.

## Repository Map

Read `references/project-map.md` before changing this repository.

Typical ownership:

- `web/`: frontend capture, crop, rubric input, coordinate setup, result UI, and auto-flow state.
- `server/`: local Node static server and proxy to the Python API.
- `grading_api/`: model API calls, validation, upload adapters, local mouse endpoints.
- `scripts/`: Windows start helpers.
- `tests/`: Python unit tests.
- `docs/`: user and release guidance.

## Workflow

1. Clarify the grading workflow:
   - Does clicking a score auto-advance to the next answer?
   - Is low confidence supposed to pause or click a skip/next button?
   - Does the model API accept base64 images, public image URLs, or both?
2. Inspect existing code before editing.
3. Preserve local safety boundaries.
4. Make focused changes.
5. Run checks:

```powershell
npm.cmd run check
python -m unittest discover -s tests
```

If the system `python` is unavailable, use the repository scripts or ask the user for their Python path.

## References

- For project layout and edit locations, read `references/project-map.md`.
- For automatic grading state and click rules, read `references/auto-flow.md`.
- For model image input and gateway issues, read `references/model-vision.md`.
- For Windows coordinate clicking and safety, read `references/mouse-automation.md`.
- For common failures, read `references/troubleshooting.md`.

Load only the relevant reference files for the user request.
