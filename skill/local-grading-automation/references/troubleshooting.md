# Troubleshooting

## Service Health

Check:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
Invoke-RestMethod http://127.0.0.1:5175/api/health
```

If web is up but grading API is down, restart with:

```powershell
scripts\start-local-tool.cmd
```

## Method Not Allowed

Usually means frontend is calling the wrong route or the Node proxy does not forward the endpoint. Check `server/index.js` route handling and Python `grading_api/server.py`.

## Model API Request Failed

Common causes:

- Missing or invalid API key.
- Gateway does not support image input.
- Gateway supports text chat but not `image_url`.
- Public image URL is blocked or expires too fast.
- Request body too large.

Check `.env`, `GRADING_IMAGE_URL_MODE`, and model capability.

## Image Is Misread

Try:

- Enlarge crop output.
- Crop tighter around the answer.
- Reduce extra UI around the answer.
- Simplify rubric text.
- Use manual standard-answer input instead of reference images.

## Auto Click Does Nothing

Check:

- Auto click is enabled.
- Score coordinate for the suggested score exists.
- Browser and grading system are on the expected monitor.
- Windows display scaling did not change after recording coordinates.
- Python API can read mouse position.

## Wrong Answer Gets Clicked

Check:

- Model response is from the active run ID.
- Pause/continue invalidates older requests.
- Score rounding matches the generated score buttons.
- Page-transition delay is long enough after score selection.
