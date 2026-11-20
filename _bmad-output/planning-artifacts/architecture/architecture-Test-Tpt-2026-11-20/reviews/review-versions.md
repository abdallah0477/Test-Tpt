# Review: Version and Technology Reality Check

- Spine: `ARCHITECTURE-SPINE.md` (draft, 2026-11-20)
- Reviewer lens: every committed technology decision checked against live registries, upstream source, and a local install test
- Date of checks: 2026-11-20
- Spine not edited

## Verdict

**Pass with one blocking fix and two required additions.** Every Stack table version exists and is the current latest. The Runner image tag exists. The model tag exists. `format` and `think=false` work as the spine assumes. One real incompatibility: **TypeScript 7.0.2 breaks openapi-typescript 7.13.0** (peer conflict at install, crash at runtime). It was reproduced locally. Two deployment gaps need to be stated: Ollama on Linux listens on 127.0.0.1 only, so `host-gateway` alone won't reach it, and the Playwright image has no Python Playwright package installed.

## Findings

### F1 [BLOCKING]: TypeScript 7.0.2 does not work with openapi-typescript 7.13.0

- `npm view openapi-typescript@7.13.0 peerDependencies` gives `{ typescript: '^5.x' }`.
- `npm install openapi-typescript@7.13.0 typescript@7.0.2` fails with **ERESOLVE** (`peer typescript@"^5.x"`).
- With `--legacy-peer-deps` the install succeeds, but the CLI crashes on start: `TypeError: Cannot read properties of undefined (reading 'createKeywordTypeNode')` at `openapi-typescript/dist/lib/ts.mjs:11`. The cause is that the TS 7 (native Go port) npm package's `"."` export is only `./lib/version.cjs`. The classic `ts.factory` compiler API is gone, and only `./unstable/*` subpaths are exposed.
- The same CLI works with `typescript@5.9.3` and with `typescript@6.0.3`, both tested locally.
- Upstream issues are still open: openapi-ts/openapi-typescript #2841 "openapi-typescript doesn't work with Typescript 7", #2867, #2872, #2723, #2818.
- On the Vite side, the official `create-vite@9.3.4` `template-react-ts` pins `typescript: ~7.0.2` with `vite ^8.3.6` and `@vitejs/plugin-react ^6.1.2`. **TS 7 + Vite 8 is fine.** Only the codegen tool conflicts.
- **Recommended change (pick one):**
  - (a, preferred) Keep TypeScript 7.0.2 for the app. Run type generation in an isolated tool scope with its own compiler, for example a separate `frontend/tools/openapi/package.json` holding `openapi-typescript@7.13.0` + `typescript@5.9.3`, or `npx -p typescript@5.9.3 -p openapi-typescript@7.13.0 openapi-typescript …`. Add a Stack row: "openapi-typescript runtime compiler: typescript 5.9.3 (isolated)".
  - (b) Pin the frontend to `typescript 5.9.3` and drop TS 7. This costs nothing in features, but it departs from the Vite template default.
  - Revisit once upstream #2841 / #2872 ships.

### F2 [REQUIRED ADDITION]: Ollama on Linux binds to 127.0.0.1, so `host-gateway` alone fails

- `extra_hosts: ["host.docker.internal:host-gateway"]` is the correct Compose syntax. It is supported since Docker Engine 20.10. Local Compose is v5.5.1.
- On native Linux Docker, `host-gateway` resolves to the bridge IP (usually `172.17.0.1`), not to loopback. Ollama v0.40.16 `envconfig.Host()` defaults to `127.0.0.1:11434` when `OLLAMA_HOST` is unset (confirmed in source), so the backend container gets connection refused.
- **Recommended change:** add to AD-19 that on Linux, Ollama must listen beyond loopback: `OLLAMA_HOST=0.0.0.0:11434` set through a systemd override (`systemctl edit ollama`), or bound to the docker bridge IP (`172.17.0.1:11434`) for a tighter setup. If `ufw` is active, allow 11434 from the docker subnet. Add a startup health check in `model_client` that names this fix in its error message. Docker Desktop (macOS, Windows, Docker Desktop on Linux) already provides `host.docker.internal`, and the extra_hosts line is harmless there.
- Security note: `0.0.0.0` exposes the unauthenticated Ollama API on the LAN. Prefer binding to the bridge IP, or state the risk.

### F3 [REQUIRED ADDITION]: The Playwright image has no Python Playwright installed in system Python

- Image config for `v1.65.2-noble-amd64`: Ubuntu 24.04, `apt-get install python3` (which is **Python 3.12**, `/usr/lib/python3.12`), `EXTERNALLY-MANAGED` removed, pip bootstrapped. Playwright is installed only into a temporary venv that is deleted after `playwright install --with-deps`. Browsers live at `/ms-playwright`.
- So the Runner Dockerfile must `pip install playwright==1.65.2 pytest-playwright==0.10.0` (or use uv) itself. The pinned version must equal the tag so it matches the baked browsers.
- Python 3.12 is supported: it is the image's system Python, and the `playwright 1.65.2` and `pytest-playwright 0.10.0` wheels require `>=3.10`.
- **Recommended change:** add one line to AD-10 or the Structural Seed Dockerfile comment saying the Dockerfile installs the pinned Python packages. Optionally note that the backend image should use `python:3.12-slim` so both containers run 3.12.

### F4 [OK, with a note]: `think=false` with qwen3:4b-instruct-2507-q4_K_M

- The model's Ollama template (blob `sha256:eade0a07…`) has no `.Think` handling. The model is a non-thinking instruct model, so it has no `thinking` capability.
- Ollama v0.40.16 `server/routes.go` returns 400 `"… does not support thinking"` only when `think` is **true** (lines 526-527, 3218-3225). `think=false` on a non-thinking model is accepted as a no-op.
- `ollama` python 0.6.3 `chat()`/`generate()` take `think: Optional[Union[bool, str]]` and `format: Optional[Union[Literal['', 'json'], JsonSchemaValue]]`. Responses expose `prompt_eval_count`, `eval_count`, `load_duration` (all AD-8 fields are available).
- Note: a future per-role `think=true` (memlog direction for test design) **will 400 on this model**. The config must only allow `think=true` on a hybrid model (qwen3:8b, qwen3.5:4b). Make `model_client` drop or reject `think=true` based on `/api/show` capabilities.
- Open upstream issue ollama/ollama #18044 "/api/generate ignores think:false and leaks raw <think>" affects thinking models on `/api/generate`. Use `/api/chat` and keep the "strip `<think>` before JSON parse" defense for challenger models.

### F5 [OK, to benchmark]: `format` = Pydantic JSON schema

- Supported by the client signature (`JsonSchemaValue`) and passed through server-side (`Format: req.Format`).
- It could not be run live (no Ollama on this machine). Pydantic v2 schemas emit `$defs`/`$ref` and `anyOf` for `Optional`. Add a Phase 1 benchmark case that sends each feature's real `model_json_schema()` and checks the output still validates. If it doesn't, inline refs before sending. Known open issues with schema plus thinking (#17434, #17987) concern thinking or cloud models, not this one.

### F6 [OK]: Runner image tag

- `curl https://mcr.microsoft.com/v2/playwright/python/tags/list` lists `v1.65.2-noble` (plus `-amd64` and `-arm64`, and `jammy` and `resolute` variants). The manifest index has linux/amd64 and linux/arm64, so Apple Silicon teammates are fine.
- Upstream note: playwright-python v1.65.2 was released 2026-11-14. The core `microsoft/playwright` repo's latest tag is v1.65.1, so the Python patch has no matching core tag. This is harmless.

### F7 [OK]: Model tags

- `registry.ollama.ai/v2/library/qwen3/manifests/4b-instruct-2507-q4_K_M` returns 200. The model layer is 2,497,280,480 bytes (about 2.5 GB, fits a 6 GB GPU with 8k context). Default params: temperature 0.7, top_k 20, top_p 0.8, repeat_penalty 1. The spine sets temperature per role, which overrides the default.
- The challenger and upgrade tags all return 200: `qwen3.5:4b`, `llama3.2:3b`, `qwen3:8b`, `qwen3:1.7b`.

### F8 [OK]: noVNC + Xvfb in the Playwright image

- `xvfb` is already in the image: Playwright `nativeDeps.ts` `ubuntu24.04-x64.tools` includes `xvfb`, installed by `playwright install --with-deps`.
- The noble archive has `novnc 1:1.3.0-2` (universe), `websockify 0.10.0+dfsg1-5build2` (main) and `x11vnc 0.9.16-10` (universe). Xvfb → x11vnc → websockify/noVNC on 6080 is the standard pattern, so the approach is sane.
- Watch-outs: run them under a small supervisor (supervisord or an entrypoint script) so Xvfb is up before Chromium. Set `DISPLAY=:99`. Use `x11vnc -shared -forever -nopw` bound inside the container, and publish 6080 only to localhost (`127.0.0.1:6080:6080`). Use `--ipc=host` or `shm_size: 1gb` for Chromium. The Playwright docs recommend `--init` and `--ipc=host` for this image.

### F9 [OK]: Stack table registry versions (all latest as of 2026-11-20)

| Package | Spine | Registry latest | requires-python / engines |
| --- | --- | --- | --- |
| fastapi | 0.165.0 | 0.165.0 | >=3.11 |
| pydantic | 2.14.4 | 2.14.4 | >=3.10 |
| uvicorn | 0.54.0 | 0.54.0 | >=3.10 |
| sse-starlette | 3.7.0 | 3.7.0 | >=3.11 |
| httpx | 0.28.1 | 0.28.1 | >=3.8 |
| ollama (python) | 0.6.3 | 0.6.3 (GitHub 2026-09-29) | >=3.8 |
| playwright | 1.65.2 | 1.65.2 | >=3.10 |
| pytest-playwright | 0.10.0 | 0.10.0 | >=3.10 |
| ruff | 0.17.6 | 0.17.6 | >=3.7 |
| react | 19.3.1 | 19.3.1 | |
| vite | 8.3.8 | 8.3.8 | node ^20.19 or >=22.12 |
| typescript | 7.0.2 | 7.0.2 (latest dist-tag) | see F1 |
| @tanstack/react-query | 5.108.2 | 5.108.2 | |
| openapi-typescript | 7.13.0 | 7.13.0 | peer typescript ^5.x (F1) |
| Ollama runtime | 0.40.16 | v0.40.16 (GitHub 2026-11-09) | |
| Node.js | 26 LTS | v26.13.1 (2026-11-10), LTS since 26.13.0 | |
| uv | "latest at setup" | 0.13.9 | |

All Python packages are compatible with 3.12.

### F10 [MINOR]: Unpinned or loosely pinned rows

- `uv`: "latest at setup" is acceptable because `uv.lock` is committed. Still, pin `uv 0.13.x` in the Dockerfiles (`COPY --from=ghcr.io/astral-sh/uv:0.13.9`) so the builds can be reproduced.
- `Node.js 26 LTS`: pin a concrete image such as `node:26.13.1-bookworm-slim` or `node:26-slim` in the frontend Dockerfile.
- `Python 3.12`: pin a patch level in the backend base image tag.

## Method (reproducible)

- `npm view <pkg> version|peerDependencies|dist-tags|exports`. Ran `npm pack create-vite@9.3.4` and read `template-react-ts/package.json`.
- Local install test in the scratchpad: openapi-typescript 7.13.0 with TS 7.0.2 (ERESOLVE, then runtime crash), with TS 5.9.3 (ok), with TS 6.0.3 (ok).
- `https://pypi.org/pypi/<pkg>/json` for versions and requires_python.
- MCR: `/v2/playwright/python/tags/list`, the manifest index, and the config blob history for `v1.65.2-noble-amd64`.
- Ollama registry: `registry.ollama.ai/v2/library/qwen3/manifests/4b-instruct-2507-q4_K_M` with its template and params blobs.
- Source read at tags: ollama `v0.40.16` `server/routes.go` and `envconfig/config.go`; ollama-python `v0.6.3` `_client.py` and `_types.py`; playwright `v1.65.1` `nativeDeps.ts`.
- Launchpad API for noble packages. nodejs.org `dist/index.json`. GitHub releases and issue search.
- Not run live: Ollama inference (Ollama isn't installed on this machine) and a Docker image build (no access to the docker socket).
