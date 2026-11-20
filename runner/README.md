# Runner

Isolated, hardened Playwright container (spine AD-11, AD-13, AD-15, AD-19, AD-20).
Headed Chromium on Xvfb, shown through noVNC on `127.0.0.1:6080`; HTTP API on
port 8100, reachable only on the internal compose network. Uses the shared
`contracts/` package for every request, result and event.

## Layout

| File | What it does |
| --- | --- |
| `app/api.py` | FastAPI: `GET /health`, `POST /inspect`, `POST /reinspect`, `POST /close`, `GET /events` |
| `app/worker.py` | One worker thread, FIFO queue, one job at a time; owns the browser and one context per session; origin allowlist |
| `app/inspect_page.py` | One inspection: load, extract, locators, screenshot, crops; failure states |
| `app/extract.py` | Deterministic JS extraction of interactive elements into Findings |
| `app/locators.py` | Locator candidates, live match counts, ranking and reliability |
| `app/events.py` | Thread-safe SSE fan-out with replay of recent events |
| `app/exchange.py` | Files on the exchange volume |
| `entrypoint.sh` | Xvfb :99, x11vnc, websockify/noVNC :6080, then uvicorn :8100 |

## API

- `POST /inspect` and `POST /reinspect` take a `contracts.InspectRequest` and answer
  `202` with `contracts.JobAccepted`. Both use the session's long-lived browser
  context (created on first use), so cookies from a manual login in the noVNC view
  are kept. `409` if the `job_id` is already known; `422` for an unsafe `job_id`
  (allowed: `[A-Za-z0-9_-]{1,64}`).
- `POST /close` takes `contracts.CloseRequest` and returns `{"session_id", "closed"}`.
- `GET /events?job_id=...` streams `contracts.SseEvent` envelopes
  (`job_queued`, `job_progress` with steps `load`, `extract`, `locators`,
  `screenshot`, then `job_done` or `job_failed`). Recent events are replayed to a
  client that connects late. Without `job_id`, all jobs are streamed.

## Exchange layout

```
{EXCHANGE_DIR}/out/{job_id}/screenshot.png          full-page screenshot (absent if the page was unreachable)
{EXCHANGE_DIR}/out/{job_id}/crops/{finding_id}.png  one per rendered Finding (not for hidden ones)
{EXCHANGE_DIR}/out/{job_id}/result.json             contracts.InspectionResult
{EXCHANGE_DIR}/out/{job_id}/DONE                    empty, written last
```

`result.json` and `DONE` are written for **every** job, also when it fails
(a crash gives status `unreachable` with a "Runner failed" reason).
`inspection.inspection_id == job_id`, `inspection.session_id` is the request's.
Paths inside the result are relative to `out/{job_id}/`: `"screenshot.png"`,
`"crops/f_001.png"`.

## Statuses

`unreachable` (navigation failed; reason names the net error and likely causes) >
`timeout` (load took longer than `load_timeout_ms`, or the job hit `JOB_TIMEOUT_MS`;
what had loaded is still extracted) > `login_required` (redirect to a login-like
path, or a visible password field with at most 8 visible elements on a page whose
URL is not itself a login page; `login_detected` is also true whenever a visible
password field is seen) > `partial` (inaccessible elements, extraction errors, or
visible iframes, which are not entered) > `complete`.

Visibility: `hidden` = not rendered for a sighted user (type=hidden, `hidden`,
display/visibility, opacity 0, zero size, off the page); `inaccessible` = rendered
but unreachable (inert, or covered at its centre by another element, checked in the
first viewport); otherwise `visible`. See `app/extract.py`.

## Environment

`EXCHANGE_DIR` (default `./exchange`), `RUNNER_HEADLESS` (default false; the
tests use true), `JOB_TIMEOUT_MS` (120000), `RUNNER_MAX_CROPS` (300).

## Run the tests natively

```sh
cd runner
uv sync
uv run playwright install chromium     # no --with-deps, no sudo
uv run pytest                          # headless
uv run ruff check . && uv run ruff format --check .
```

Run the API natively: `RUNNER_HEADLESS=true uv run uvicorn app.api:app --port 8100`.

## Container

`docker compose up --build runner`, then open `http://127.0.0.1:6080/vnc.html?autoconnect=1&resize=scale`
(the UI can embed that URL). Hardening is in `docker-compose.yml`: non-root,
`cap_drop: [ALL]`, `no-new-privileges`, read-only root with tmpfs `/tmp`,
`pids_limit`, `mem_limit`, `shm_size: 1gb`, `tini` as PID 1 (in the image), only the `exchange` volume mounted.
