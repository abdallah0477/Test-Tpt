# Phase 1 submission: Human-in-the-Loop Web Testing Assistant

Architecture and guided inspection (Week 9). Each item below is one point of the brief's "What to submit" list.

| Brief item | File(s) |
|---|---|
| Short design document: component diagram, data flow, approval gates, resource assumptions, path to generation / execution / maintenance | [`docs/design-document.md`](docs/design-document.md) |
| Runnable source code and dependencies | [`source-code.zip`](source-code.zip): the full repository; dependencies are pinned in `backend/uv.lock`, `runner/uv.lock`, `frontend/package-lock.json` and the Dockerfiles |
| Setup instructions | [`README.md`](README.md) |
| Model configuration | [`config.toml`](config.toml) (model `qwen3:4b-instruct-2507-q4_K_M` via Ollama), [`.env.example`](.env.example), [`docker-compose.yml`](docker-compose.yml) |
| No API secrets | No keys anywhere; `.env` is gitignored and not included |
| Short demonstration | Demo walkthrough: [`docs/demo-script.md`](docs/demo-script.md). Recording: *add the video file here* |
| Sample structured inspection output | [`docs/samples/inspection.json`](docs/samples/inspection.json): 13 Findings with attributes, visibility, container, fingerprint and ranked, verified locators |
| Model usage / timing evidence | [`docs/samples/model_calls.json`](docs/samples/model_calls.json) (per-call model, setup, tokens, response and load time, validation outcome), [`docs/resources.md`](docs/resources.md) and [`docs/benchmark-results.json`](docs/benchmark-results.json) (16-case benchmark) |

## Feasibility evidence at a glance

- Model: `qwen3:4b-instruct-2507-q4_K_M` (Q4_K_M, 2.5 GB), Ollama 0.40.16, thinking off, num_ctx 8192
- Hardware: NVIDIA RTX 3060 Laptop (6 GB VRAM), Intel i7-11800H, 14 GB RAM; peak VRAM 3.9 GB
- Benchmark over 16 Scope summaries on 3 real Inspections: 100% valid JSON on the first attempt and a 100% grounding pass; per answer 4.2 s mean and 9.0 s p95; 66.5 tokens/s
- Sample session: clarification call 1,546 + 80 tokens in 1.6 s (failed validation, retried), retry 1,707 + 74 tokens in 1.0 s (passed), summary 582 + 202 tokens in 2.8 s (passed)

## Run it

Unzip `source-code.zip` and follow `README.md` (Ollama on the host, then `docker compose up --build`, then open http://127.0.0.1:5173).
