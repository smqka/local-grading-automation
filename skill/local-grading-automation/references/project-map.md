# Project Map

Use this file when modifying the included local grading assistant.

## Frontend

`web/index.html`

- Main UI structure.
- Capture panel, rubric form, result panel, auto-click panel, history panel.

`web/app.js`

- Screen capture and crop logic.
- Local storage for rubric and coordinate settings.
- Manual grading request.
- Automatic grading loop.
- Coordinate recording and click requests.

`web/styles.css`

- Layout and responsive styling.

## Node Server

`server/index.js`

- Serves static frontend files.
- Proxies `/api/grade-answer` to Python `/api/grade`.
- Proxies `/api/parse-reference` to Python `/api/parse-reference`.
- Proxies mouse endpoints to Python.

`server/config.js`

- Reads frontend port, API URL, token, and proxy body limits.

## Python API

`grading_api/server.py`

- Local HTTP server.
- Health endpoint.
- Grading endpoints.
- Mouse position and click endpoints.

`grading_api/openai_client.py`

- OpenAI-compatible model calls.
- Image input formatting.
- Upload-to-URL fallback.
- Prompt and output parsing.

`grading_api/validation.py`

- Request validation.
- Model result validation.
- Score range and confidence safety.

`grading_api/service.py`

- Service layer between HTTP handlers and model client.

## Scripts

`scripts/start-local-tool.cmd`

- Starts web and Python API if ports are free.

`scripts/run-grading-api.cmd`

- Starts Python API and logs to `logs/grading-api.log`.

`scripts/run-web.cmd`

- Starts Node server and logs to `logs/web.log`.

## Tests

Run:

```powershell
npm.cmd run check
python -m unittest discover -s tests
```
