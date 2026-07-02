# Mouse Automation

Use this file when modifying coordinate recording or local click execution.

## Browser Boundary

Browser JavaScript cannot safely control the mouse outside the browser. Use a local backend endpoint for operating-system-level mouse actions.

## Local API Rules

- Bind to `127.0.0.1`.
- Validate coordinates are finite numbers.
- Validate coordinates are inside the current virtual screen bounds.
- Keep click endpoints behind the same local token mechanism if one is configured.
- Do not expose click endpoints on a public network.

## Coordinate UX

Use delayed coordinate recording:

1. User clicks "record".
2. UI announces a short countdown.
3. User moves the mouse to the target button.
4. Backend reads current cursor position.

This avoids recording the tool's own button position.

## Score and Skip Coordinates

- Record one coordinate per score value.
- Record a skip coordinate only if low-confidence auto-skip is enabled.
- If score selection auto-advances, high-confidence automation should click only the score.

## Testing

Do not run destructive or real click tests without user consent. Prefer testing:

- Mouse-position endpoint.
- Coordinate validation.
- Dry-run UI logic.
- Manual one-click tests chosen by the user.
