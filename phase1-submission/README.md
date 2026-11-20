# Human-in-the-Loop Web Testing Assistant (Phase 1)

The assistant inspects a web page in a visible, isolated browser and lists every interactive element it finds (a *Finding*) with verified locators. The tester sets a testing goal and selects elements (the *Scope*). A local model then gives a grounded summary: every claim cites an observed element, and anything it can't back up is withheld. Each model call shows its tokens and response time.

- Design: [`docs/design-document.md`](docs/design-document.md)
- Model, hardware and measured limits: [`docs/resources.md`](docs/resources.md)
- Demo walkthrough: [`docs/demo-script.md`](docs/demo-script.md)
- Sample outputs: [`docs/samples/inspection.json`](docs/samples/inspection.json), [`docs/samples/model_calls.json`](docs/samples/model_calls.json)
- Model configuration: [`config.toml`](config.toml)

## What runs where

| Part | Runs in | Address |
|---|---|---|
| Web UI (React + TypeScript, Vite) | Docker `frontend` | http://127.0.0.1:5173 |
| Backend API (FastAPI) | Docker `backend` | http://127.0.0.1:8000 |
| Runner (Playwright + Chromium, hardened) | Docker `runner` | API internal only; live view http://127.0.0.1:6080 |
| Model `qwen3:4b-instruct-2507-q4_K_M` | **Ollama, natively on the host** (so it can use the GPU) | port 11434 |

All published ports bind to `127.0.0.1` only. No paid APIs are used.

## 1. Prerequisites

- **Docker** with Compose v2 (`docker compose version`). On Linux: Docker Engine. On macOS and Windows: Docker Desktop.
- **Ollama** 0.40 or newer: https://ollama.com/download
- About 10 GB free disk (images + model). A GPU with ≥ 4 GB VRAM is recommended; the model also runs on CPU, but more slowly.

## 2. Pull the model

```sh
ollama pull qwen3:4b-instruct-2507-q4_K_M
```

This is the only model the project uses (both the `assistant` and `codegen` roles in `config.toml`).

## 3. Make Ollama reachable from the containers

The backend container calls Ollama at `http://host.docker.internal:11434`.

**macOS / Windows (Docker Desktop):** nothing to change. Start the Ollama app (or `ollama serve`); Docker Desktop forwards `host.docker.internal` to the host's localhost.

**Linux:** Ollama listens on `127.0.0.1` by default, which containers can't reach. Make it listen on the Docker bridge address (`172.17.0.1`, check with `ip -4 addr show docker0`):

```sh
# one-off, in a terminal
OLLAMA_HOST=172.17.0.1:11434 ollama serve
```

If Ollama is installed as a systemd service, set it there instead:

```sh
sudo systemctl edit ollama
# add:
#   [Service]
#   Environment="OLLAMA_HOST=172.17.0.1:11434"
sudo systemctl restart ollama
```

Avoid `OLLAMA_HOST=0.0.0.0` on a shared network: it exposes Ollama to every machine on the LAN.

Check it: `curl http://172.17.0.1:11434/api/tags` (Linux) or `curl http://127.0.0.1:11434/api/tags` (macOS/Windows) should list the model.

## 4. Configure (optional)

```sh
cp .env.example .env
```

The defaults work without a `.env`. Use it to override settings (for example `OLLAMA_BASE_URL`, or any key as `TPT__<SECTION>__<KEY>`), and on Linux to set `HOST_UID` / `HOST_GID` if your user is not uid/gid 1000 (`id -u`, `id -g`), so files in `data/` stay yours. The cloud fallback is off (`[cloud] enabled = false`); its key, if you ever enable it, goes only in `.env`, which is gitignored.

## 5. Start

```sh
docker compose up --build
```

The first build downloads the Playwright image and takes a few minutes. Add `-d` to run in the background; stop with `docker compose down`.

Ready when:

- `curl http://127.0.0.1:8000/api/v1/health` returns `{"status":"ok"}`
- the UI header shows **Model ready (qwen3:4b-instruct-2507-q4_K_M, Ollama …)**

## 6. Use it

1. Open **http://127.0.0.1:5173**.
2. Enter a page URL and click **Start inspection**. The Runner's browser opens the page, and you can watch it in the live view embedded in the UI (or directly at http://127.0.0.1:6080/vnc.html?autoconnect=1&resize=scale).
3. Look through the numbered screenshot, the Findings table and a Finding's detail panel (locators with live match counts). **Export JSON** downloads the Inspection.
4. Write a **Testing goal**, tick Findings into the **Scope** (or use the filters and **Apply to Scope**), then click **Summarize Scope**. If the goal is vague, the assistant asks a clarification question first.
5. The answer shows *Observed / Inferred meaning / Unverified / Next step* with clickable evidence and a usage badge. **Export usage** downloads every model call record.

If a page needs a login, sign in by hand in the live browser view, then click **Re-inspect**. The system never asks for or stores credentials.

**Inspecting a page served from your own machine:** the browser runs inside a container, so `127.0.0.1` there is the container itself. Serve the page on the Docker bridge and use `host.docker.internal`, for example with the bundled test pages:

```sh
python3 -m http.server 8088 --bind 172.17.0.1 --directory backend/scripts/bench_pages   # Linux
python3 -m http.server 8088 --directory backend/scripts/bench_pages                     # macOS/Windows
```

then inspect `http://host.docker.internal:8088/signup.html`.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| UI shows **Model not reachable** | Ollama isn't running or isn't reachable from Docker. Linux: start it with `OLLAMA_HOST=172.17.0.1:11434` (step 3). Check with `docker compose exec backend python -c "import urllib.request;print(urllib.request.urlopen('http://host.docker.internal:11434/api/tags').read()[:200])"`. |
| Model not found | Run `ollama pull qwen3:4b-instruct-2507-q4_K_M` on the host. |
| `permission denied ... docker.sock` (Linux) | Your user isn't in the `docker` group: `sudo usermod -aG docker $USER`, then **log out and back in** (or reboot). |
| First summary is slow | First-call warm-up: the model is loaded into VRAM on first use (a few seconds, longer on the very first load from disk). The backend warms it at startup and keeps it loaded for 30 min. Later calls take about 4 s on average (see `docs/resources.md`). |
| Inspection says **Page unreachable** for a local page | The URL points at `127.0.0.1`/`localhost`. Use `host.docker.internal` and serve on the bridge address (see above). |
| Live view is blank | Wait until the `runner` container is healthy (`docker compose ps`), then reload; the view connects to `127.0.0.1:6080`. |
| Port already in use | Something else uses 5173, 8000 or 6080. Stop it, or change the host side of the port in `docker-compose.yml`. |
| `data/` files owned by another user (Linux) | Set `HOST_UID` / `HOST_GID` in `.env` to your `id -u` / `id -g`. |

## Development (optional)

Tests run natively with [uv](https://docs.astral.sh/uv/) and Node (the frontend image uses Node 26):

```sh
cd backend && uv sync && uv run pytest && uv run ruff check .
cd runner  && uv sync && uv run playwright install chromium && uv run pytest
cd frontend && npm ci && npx vitest run
```

The model benchmark (`backend/scripts/benchmark.py`) rewrites the results section of `docs/resources.md`; see that file.

## Layout

```
backend/    FastAPI app: v1/<feature>/ folders, utils/ (model_client, agent_loop, store, gates, …)
runner/     isolated Playwright Runner (see runner/README.md)
frontend/   React + TypeScript UI
contracts/  shared data shapes used by backend and Runner; frontend types are generated from them
config.toml all tunables and the model configuration (no secrets)
data/       stored Sessions, Inspections and model call records (gitignored)
docs/       design document, resources and benchmark, demo script, sample outputs
```
