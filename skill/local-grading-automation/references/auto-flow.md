# Automatic Grading Flow

Use this file when changing confidence thresholds, pause/continue behavior, screenshot refresh, or click automation.

## Required Event Order

1. Capture or refresh the current crop.
2. Send the current crop to the model.
3. Wait for the current model response.
4. Verify the current run ID is still active.
5. Decide action from confidence and review flags.
6. Click or pause.
7. After page transition, refresh the next crop.

Never use a fixed timer to wait for model output. Timers are only acceptable after a click that changes the grading page.

## Decision Rules

- High confidence: `confidence >= threshold` and `needs_review=false` and score is finite.
- High confidence action: click the score coordinate.
- Low confidence action `review`: pause and wait for the user.
- Low confidence action `skip`: click the user-recorded skip coordinate.

If the grading system auto-advances after score selection, do not click a next button after score selection.

## Stale Response Guard

Maintain a run ID or cancellation token. Increment it when:

- Starting a new run.
- Pausing.
- Continuing after manual review.
- Stopping capture.

When a model response returns, ignore it if its run ID no longer matches the active run.

## Manual Review

When paused for review, keep the latest result visible. The user can:

- Manually handle the current answer in the grading system.
- Click continue after the grading system has moved to the next answer.
- Adjust the confidence threshold or low-confidence action.

## Screenshot Delay

Show page-transition delay to users in seconds. Internally convert to milliseconds. This delay is for waiting after score/skip clicks, not for waiting on the model.
