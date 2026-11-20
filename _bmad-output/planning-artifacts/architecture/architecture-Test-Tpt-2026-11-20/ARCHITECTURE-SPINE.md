---
name: 'Human-in-the-Loop Web Testing Assistant'
type: architecture-spine
purpose: build-substrate
altitude: initiative
paradigm: 'vertical-slice feature folders (utils/ + v1/<feature>) over a gated, append-only artifact workflow'
scope: 'Whole system. Phase 1 (inspection, guided interaction, grounded assistant, usage records) is built now; Phase 2 (test design, codegen, execution, maintenance, versioning) is fixed here so it builds on the same foundation'
status: final
created: '2026-11-20'
updated: '2026-11-20'
binds: [FR-1, FR-2, FR-3, FR-4, FR-5, FR-6, FR-7, FR-8, FR-9, FR-10, FR-11, FR-12, FR-13, FR-14, FR-15, FR-16, FR-17, FR-18, FR-19, FR-20, FR-21, FR-22, FR-23, FR-24, FR-25, FR-26, NFR-1, NFR-2, NFR-3, NFR-4, NFR-5, NFR-6, P2-TestDesign, P2-Codegen, P2-Execution, P2-Maintenance, P2-Versioning]
sources:
  - GenAI_Fall26_project.md
  - _bmad-output/planning-artifacts/prds/prd-Test-Tpt-2026-11-20/prd.md
  - _bmad-output/planning-artifacts/prds/prd-Test-Tpt-2026-11-20/addendum.md
companions:
  - .memlog.md
  - reviews/
---

# Architecture Spine: Human-in-the-Loop Web Testing Assistant

Phase 2 items with no PRD yet use `P2-*` ids, taken from the brief's Phase 2 rubric rows.

## Design Paradigm

**Vertical-slice feature folders over a gated, append-only artifact workflow.** There are no service, repository or controller layers. Each feature is one folder under `backend/app/v1/`, and shared helpers live in `backend/app/utils/`. Features don't call each other. They work together only by reading and writing **versioned artifacts** through `utils/store.py`, and every action that crosses a human approval point is checked by `utils/gates.py`. Data shapes shared by the backend and the Runner live once, in the `contracts/` package.

```mermaid
flowchart LR
  subgraph v1["backend/app/v1/ (features)"]
    INS[inspection]
    SES[session]
    AST[assistant]
    TD[test_design]
    CG[codegen]
    EX[execution]
    MT[maintenance]
    VR[versions]
    US[usage]
  end
  subgraph utils["backend/app/utils/"]
    STORE[store]
    MC[model_client]
    RC[runner_client]
    LOOP[agent_loop]
    PR[prompting]
    GATES[gates]
    EVT[events]
    CONF[confidence]
  end
  CT[contracts/ shared Pydantic models]
  RUN[runner/app]
  v1 --> utils
  v1 --> CT
  utils --> CT
  RUN --> CT
  MC --> OLLAMA[(Ollama on host)]
  RC --> RUN
  STORE --> DATA[(data/)]
```

Dependency rule: `v1/*` → `utils/*` → `contracts/`, and `runner/` → `contracts/`. Nothing imports `v1/*`, and no `v1/X` imports `v1/Y`. `contracts/` imports nothing from the project.

## Invariants & Rules

### AD-1: Feature folders, no cross-feature imports [ADOPTED]
- **Binds:** all backend code
- **Prevents:** features tangling through each other's internals; two copies of the same helper drifting apart.
- **Rule:** Each feature lives in `backend/app/v1/<feature>/`, holding its routes, prompts, logic and **request/response-only** schemas. Code used by two or more features goes in `backend/app/utils/`. A feature reads another feature's output only as a stored artifact, through `store`, and never by importing that feature.

### AD-2: Single gateways [ADOPTED]
- **Binds:** all features; FR-17, FR-18, NFR-6, AD-10
- **Prevents:** a model call that skips the usage record; Playwright code inside the backend; files written with no versioning or locking.
- **Rule:** `utils/model_client.py` is the only code that calls a model runtime. `utils/runner_client.py` is the only code that talks to the Runner. `utils/store.py` is the only code that reads or writes `data/`. `utils/gates.py` is the only code that reads or writes approvals. The backend never imports `playwright`.

### AD-3: Shared contracts package [ADOPTED]
- **Binds:** backend, Runner, frontend (through OpenAPI); every stored artifact
- **Prevents:** a feature or the Runner redefining Finding, Inspection, Session, version, run result or event shapes in its own way.
- **Rule:** `contracts/` is a local Python package installed into both the backend and Runner images. It holds every **stored** model and every model that **crosses the Runner boundary**: Session, Inspection, Finding, LocatorCandidate, FindingRef, the version envelope, TestPlan and TestCase, TestCode, Repair, RunResult, ModelCallRecord, AssistantResponse, Approval, and the SSE event union. It also holds `render_locator()`, the only function that turns a LocatorCandidate into Python code. Feature folders may define only request/response models that are never stored.

### AD-4: JSON file storage with one owner per path [ADOPTED]
- **Binds:** FR-8, P2-Versioning, all features
- **Prevents:** corrupted or half-written files; lost updates when two requests write the same file; two features owning one entity.
- **Rule:** All state is JSON under `data/`. The backend runs as **one uvicorn worker**. `store.py` provides exactly four write modes, each atomic (write to a temp file, fsync, rename) and locked per path:
  - `write_once(path)`, which fails if the file exists;
  - `append_version(kind, id, content)`, covered by AD-5;
  - `update_json(path, fn, expected_rev)`, which increments `rev`, and returns 409 if `expected_rev` is stale (the API passes `If-Match`);
  - `append_jsonl(path, record)`.

  Each path has one owner and one mode:

| Path | Owner (only writer) | Mode |
|---|---|---|
| `sessions/{ses}/session.json` | `v1/session` | update_json |
| `sessions/{ses}/approvals.jsonl` | `utils/gates` | append_jsonl |
| `sessions/{ses}/responses/{resp}.json` | `utils/agent_loop` | write_once |
| `inspections/{ins}/inspection.json` + blobs | `v1/inspection` (imports Runner output) | write_once, at terminal status |
| `artifacts/test_plan/{tp}/v{n}.json` | `v1/test_design` (edits), `v1/versions` (restore) | append_version |
| `artifacts/test_code/{code}/v{n}.json` | `v1/codegen`, `v1/maintenance` (repair), `v1/versions` (restore) | append_version |
| `artifacts/repair/{rep}/v{n}.json` | `v1/maintenance` | append_version |
| `runs/{run}/run.json` + blobs | `v1/execution` (imports Runner output) | write_once |
| `runs/{run}/feedback.jsonl` | `v1/execution` | append_jsonl |
| `usage/model_calls.jsonl` | `utils/model_client` | append_jsonl |

Binary files (screenshots, crops, traces) are referenced by a path relative to `data/`. The Runner never writes to `data/`.

### AD-5: Versions: one envelope, canonical hash, store allocates numbers [ADOPTED]
- **Binds:** P2-Versioning, P2-TestDesign, P2-Codegen, P2-Maintenance, AD-6
- **Prevents:** lost history; two writers both creating `v4`; approval hashes that never match because the two sides hash different bytes.
- **Rule:** Every version file uses the envelope `{kind, id, version, session_id, created_at, created_by, derived_from: [{kind,id,version}], restored_from: int|null, content_sha256, content}`. `store.append_version` alone assigns `version` (n+1, under the lock, with exclusive file creation) and computes `content_sha256` as the SHA-256 of **canonical JSON of `content` only** (`sort_keys=True`, `separators=(",",":")`, UTF-8). Features never compute `n` or hashes. Restoring `vK` writes a new version with `restored_from: K`. A diff compares the `content` of two versions as pretty-printed canonical JSON, or as the rendered `.py` for test code. A rescan creates a **new** Inspection, and a stored Inspection is never changed.

### AD-6: Approvals and action preconditions [ADOPTED]
- **Binds:** FR-23, P2-TestDesign, P2-Codegen, P2-Execution, P2-Maintenance, AD-15
- **Prevents:** running something other than what the tester approved; gate checks scattered across features; the UI being the only thing that enforces approval.
- **Rule:** An Approval record is `{gate, session_id, target: {kind,id,version}|{origin}, content_sha256|null, approved_at}`, written only by `gates.record()`. Every gated action calls `gates.require(action, …)` first, which checks the preconditions below against `approvals.jsonl` and the current version hash:

| Action | Preconditions |
|---|---|
| Runner loads a URL | G0 for its origin |
| `codegen.generate` | G1 on that test_plan version, with no expected result left as `assumption` |
| `execution.run` | validation passed (AD-13) + G2 + G3 on that test_code version + G0 for every origin it uses |
| `execution.rerun` (same code version) | G4 for this rerun |
| `maintenance.apply` | G5 on that repair version. The resulting test_code version counts as G2-reviewed (the repair diff was the review) but still needs validation and G3 before it can run. |

Any edit creates an unapproved version, so the gate locks again. Open Clarification requests (FR-13, test design, ambiguous rescan matches) block the step until the tester answers or explicitly skips.

### AD-7: Model output is validated JSON before anyone sees it [ADOPTED]
- **Binds:** FR-14–FR-17, NFR-1, P2-TestDesign, P2-Codegen, P2-Maintenance
- **Prevents:** prose that can't be checked; unvalidated tokens reaching the tester; each feature retrying in its own way.
- **Rule:** Every model call asks for schema-constrained JSON (Ollama `/api/chat` with `format` = the feature's Pydantic JSON schema). Findings are cited only by FindingRef (AD-11). `utils/agent_loop.py` runs validate (schema, cited refs exist and are in Scope, attribute values match exactly), then retries with the errors fed back (default **2 retries**, configurable), then blocks claims that still fail. It stores the AssistantResponse with its validation outcome. Nothing is streamed. The UI shows pipeline steps over SSE. The backend turns the validated JSON into text. The model never chooses workflow transitions, matches or actions, and gets no tools.

### AD-8: Models are bound by role in config [ADOPTED]
- **Binds:** NFR-2, NFR-4, FR-26, FR-18
- **Prevents:** model names hard-coded in features; thinking or context settings that vary between calls.
- **Rule:** `config.toml` maps roles to `{provider, model, think, num_ctx, temperature}`. The roles are `assistant` and `codegen`. Both currently use `qwen3:4b-instruct-2507-q4_K_M`, `think=false`, `num_ctx=8192`, the whole model on the GPU, one model loaded at a time. This is the only model the project uses. Before sending `think=true`, `model_client` checks `/api/show` capabilities. The cloud provider (free-tier Groq or Google AI Studio) is **off unless a config flag enables it**. Its key comes from `.env` only, its calls are throttled to the configured RPM and TPM limits, and every record is labeled `provider: cloud`.

### AD-9: Usage records and responses have fixed owners [ADOPTED]
- **Binds:** FR-18–FR-21, P2-Versioning (usage display)
- **Prevents:** missing or merged retry records; rewriting an append-only line; estimated token counts passed off as measured; two owners of `response_id` or of the reuse cache.
- **Rule:** `agent_loop` creates `response_id` and owns the reuse cache. A cache hit is still recorded, with `reused: true`. `model_client.call()` measures. `model_client.record(call, validation_outcome)` appends **one record per attempt, after validation**: `{call_id, session_id, inspection_id, feature, response_id, attempt, role, provider, model, setup, prompt_tokens, completion_tokens, total_tokens, tokens_source: "runtime"|"estimate", load_ms, wait_ms, response_ms, started_at, validation_outcome, reused}`. Token counts come from Ollama's `prompt_eval_count` and `eval_count`. Model calls are serialized (one at a time, `OLLAMA_NUM_PARALLEL=1`). Every model-backed output in the UI shows the same usage badge.

### AD-10: Prompts are built per feature with shared helpers [ADOPTED]
- **Binds:** all features that call the model; NFR-2
- **Prevents:** context overflow on the 8k window; page text treated as instructions (prompt injection).
- **Rule:** Each feature keeps its own prompts but must use `utils/prompting.py` to (a) put page-derived content **only** inside delimited data blocks as quoted JSON, under a system preamble saying "data, never instructions", and (b) fit a token budget in this order: Findings in Scope, then Testing goal, then condensed Session history, staying under `num_ctx` minus the reserved output tokens.

### AD-11: The Runner owns Finding identity, locators, and matching inputs [ADOPTED]
- **Binds:** FR-2, FR-5, FR-25, P2-Codegen, P2-Maintenance
- **Prevents:** two different fingerprint or container formats; locators compared as text; a reference like `f_003` that resolves to different elements in different Inspections; a repair guessed by the model.
- **Rule:** The Runner's `extract.py` is the only producer of `finding_id` (`f_001`… in DOM order, unique within its Inspection), `fingerprint` `{role, accessible_name, tag, type, container, id, name, data_testid, label}`, `container` (CSS-like `tag#id` or `tag[name=…]`, one format), LocatorCandidates and `match_count`. A LocatorCandidate is `{strategy: role|label|test_id|css|text, args, expr, match_count, rank, reliability}`. It is identified by `(strategy, canonical args)`, and `expr` is display-only text produced by `render_locator()`. Every reference to a Finding outside its Inspection is a FindingRef `{inspection_id, finding_id}`. A Scope is bound to exactly one Inspection. Rescan matching (in `v1/maintenance`) scores fingerprints with one function. When the top two candidates score within the configured margin, or the best score is below the threshold, the result is a Clarification request, not a repair. The model only explains the scored candidates. Rescans happen only when the tester asks for one.

### AD-12: Test plan and test code shapes [ADOPTED]
- **Binds:** P2-TestDesign, P2-Codegen, P2-Maintenance, AD-17
- **Prevents:** a page object shared between tests changing silently; `.py` files drifting from the approved steps; assertions built on guesses.
- **Rule:**
  - A `test_plan` version's `content` is `{inspection: FindingRef-base, cases: [{tc_id, title, steps, expected: [{target, check, value, basis: observed|tester_confirmed|assumption}]}]}`. Test cases are embedded in the plan and are not versioned separately.
  - A `test_code` version's `content` is `{page_objects: {page: {member: LocatorCandidate-identity}}, cases: {tc_id: steps+asserts JSON}}`. The `.py` files are **rendered** from this content and are never the source of truth.
  - In the UI the rendered code is read-only for review. Changes go through structured edits that create a new version.

### AD-13: Validation before execution [ADOPTED]
- **Binds:** FR-5, FR-24, P2-Codegen, P2-Execution
- **Prevents:** running tests whose locators were never observed or match several elements; generated code that reaches the host.
- **Rule:**
  - **Locator ranking:** role/label first, then test id, then CSS. XPath and positional selectors are never generated automatically. Only `match_count == 1` may be ranked best.
  - **Code checks before G3:** the rendered code must pass `ast.parse`, `ruff check`, and an **AST allowlist** (imports limited to `pytest`, `playwright.sync_api`, `re` and the generated page objects; no `os`, `subprocess`, `socket`, `open`, `eval`/`exec` or `__import__`).
  - **Locators:** every page-object locator must exist, by identity, among the source Inspection's candidates **and** match exactly one element on the live page (a Runner check).
  - **Expected results:** targets an action reveals (messages, URL, headings) are checked at run time and are exempt from the pre-run single-match check.
  - **Escaping:** every value placed into code goes through one escaping helper (`repr` or JSON literal).
  - **Result:** stored with the code version.

### AD-14: Contract sync, REST plus typed SSE [ADOPTED]
- **Binds:** backend ↔ frontend, backend ↔ Runner
- **Prevents:** TypeScript types drifting from the API; each feature inventing its own progress messages.
- **Rule:** Frontend types are generated from FastAPI's OpenAPI schema with `openapi-typescript` and never edited by hand. Actions use REST under `/api/v1/…`. Progress goes over SSE as a discriminated union from `contracts/`, exposed in the OpenAPI schema, with the envelope `{event, job_id, step, status, ts, data}`. Errors use `{error: {code, message, details}}`. Optimistic concurrency uses `If-Match: <rev>`.

### AD-15: Approved target origins [ADOPTED]
- **Binds:** FR-1, FR-7, FR-9, P2-Execution, P2-Maintenance
- **Prevents:** inspection or tests reaching sites outside the target; two sources of truth for the allowed origins.
- **Rule:** Starting an Inspection of a URL calls `gates.record()` with G0 for its origin. Allowed origins exist **only** in `approvals.jsonl`. `runner_client` sends `gates.approved_origins(session)` with every job. The Runner aborts browser requests outside those origins in its own `conftest` and inspection context (`context.route`). Moving to a new origin, for example the modified instructor site, needs a new G0. Rescans still compare by fingerprint across origins.

### AD-16: Clarification confidence is computed by code [ADOPTED]
- **Binds:** FR-13, FR-14
- **Prevents:** relying on the model's opinion of itself; `assistant` and `session` scoring confidence differently.
- **Rule:** `utils/confidence.py` scores observable signals: the goal references existing Findings or containers, Scope is non-empty, the goal names an action, and the number of open ambiguities. The model may list ambiguities but never supplies the score. `v1/session` stores `{confidence, actionable, clarification: [{clr_id, question, answer|skipped, refs}]}` in `session.json`. Other features only read it. The threshold is in config, and the score is always returned to the UI.

### AD-17: Test intent is preserved [ADOPTED]
- **Binds:** P2-Codegen, P2-Execution, P2-Maintenance
- **Prevents:** a repair or revision that weakens an assertion to make a test pass.
- **Rule:** A G5 repair may change only `content.page_objects` locators. `content.cases` must be canonical-JSON identical to the source version, and `maintenance.apply` checks this. Any change to steps or expected results is a new test_plan version that goes back through G1. A test that fails because the application is wrong is reported as failed and is never auto-revised.

### AD-18: Separate, labeled timings [ADOPTED]
- **Binds:** FR-19, FR-21, P2-Execution, P2-Versioning
- **Prevents:** model time and browser time added together; reused results counted as fresh calls.
- **Rule:** Model `response_ms`, `load_ms` and `wait_ms` (AD-9) are stored and shown separately from the Runner's `browser_ms` and per-test `duration_ms`. Session and page averages (grouped by `inspection_id`) count only records with `reused == false`.

### AD-19: Runner container and exchange protocol [ADOPTED]
- **Binds:** FR-1–FR-7, FR-9, P2-Execution, P2-Maintenance
- **Prevents:** generated code reaching host files or the shell; one job overwriting another's files; mismatched ids and result formats.
- **Rule:**
  - **Image:** `FROM mcr.microsoft.com/playwright/python:v1.65.2-noble`, then `pip install playwright==1.65.2 pytest-playwright==0.10.0`. The image tag always equals the pinned version.
  - **API:** `POST /inspect`, `/reinspect`, `/run_tests`, `/close`, plus `GET /events` (SSE). It runs on the internal compose network only.
  - **Queue:** **one job at a time**, FIFO, with per-job and per-test timeouts from config.
  - **Hardening:** non-root user, `cap_drop: [ALL]`, `no-new-privileges`, read-only root filesystem with tmpfs, `pids_limit`, `mem_limit`, `shm_size: 1gb`, `init: true`, and no `docker.sock`.
  - **Exchange volume:**
    - `tests/{job_id}/` holds the rendered files and a `manifest.json` with the hash and allowed origins. It is never modified once written.
    - `out/{job_id}/result.json` is a contracts RunResult or Inspection, with per-test status, duration, error, stack, screenshot and trace paths. A `DONE` marker is written last.
    - The backend allocates the `ins_`/`run_` id and uses it as `job_id`. It imports from `out/` only after `DONE`, then cleans up.
  - **Runner-owned conftest:** the Runner owns `conftest.py`, which creates a fresh context, applies the route allowlist and records timings. Codegen never emits fixtures. The Runner refuses a job whose manifest hash doesn't match.
  - **Display:** headed Chromium on Xvfb, shown through **noVNC** (x11vnc + websockify) on `127.0.0.1:6080`, which the UI can embed. X11 passthrough is an optional mode on Linux only.
  - **Host access:** `extra_hosts: host.docker.internal:host-gateway`, so instructor sites hosted on the laptop are reachable.

### AD-20: Sessions and browser contexts [ADOPTED]
- **Binds:** FR-7, FR-9, FR-10, FR-13, P2-Execution
- **Prevents:** test results depending on state left over from inspection; goal or scope state duplicated across features.
- **Rule:** A Session holds the Testing goal history, current Scope (one Inspection plus FindingRefs) and filters, plus the clarification data from AD-16, all in `session.json` and owned by `v1/session`. The Runner keeps one long-lived inspection context per Session for manual login and re-inspection (FR-7). **Every test run gets a fresh browser context.** Contexts are never shared between inspection and test runs. Any future mechanism for logging in during tests must enter only through the Runner's conftest and never persist a secret under `data/`.

### AD-21: One-command deployment, with Ollama on the host [ADOPTED]
- **Binds:** NFR-4, NFR-5, FR-26, all components
- **Prevents:** setups that only work on one teammate's machine; trying to give Docker the GPU on macOS; a backend container that can't reach Ollama on Linux.
- **Rule:**
  - **Start:** `docker compose up` starts `frontend`, `backend` and `runner`. Published ports bind to `127.0.0.1`.
  - **Ollama:** runs natively on each machine (CUDA on Linux and Windows, Metal on macOS). The backend reaches it at `http://host.docker.internal:11434` (`extra_hosts: host-gateway`).
  - **Linux:** Ollama must listen on the Docker bridge, with `OLLAMA_HOST=172.17.0.1:11434` set in a systemd override, never `0.0.0.0`.
  - **Startup:** the backend health-checks Ollama and prints this fix if it can't connect.
  - **Secrets:** live only in a gitignored `.env`, with `.env.example` committed.
  - **Resources:** `docs/resources.md` records, per machine, the model, quantization, VRAM and RAM in use, context size, measured latency and tokens/s, and cloud rate limits. It is filled in from the benchmark.

## Consistency Conventions

| Concern | Convention |
| --- | --- |
| IDs | The backend allocates prefixed ULIDs: `ses_`, `ins_`, `tp_`, `tc_`, `code_`, `run_`, `rep_`, `call_`, `resp_`, `clr_`. Findings use `f_001` within an Inspection. A version is an integer `n` ≥ 1, assigned by `store`. |
| Timestamps | ISO-8601 UTC with `Z`. Durations are integer `_ms`. |
| JSON keys | `snake_case` in files and API. TypeScript uses the generated types as they are. |
| Names | Python modules in `snake_case`, React components in `PascalCase.tsx`. One feature name is reused across the `v1/` folder, the `/api/v1/<feature>` prefix and the `frontend/src/features/` folder. |
| Locator text | Playwright **Python** syntax, produced only by `contracts.render_locator()`, both in the UI and in code. |
| Evidence vs inference | Assistant output fields are tagged `observed`, `inferred`, `unverified` or `next_step`. Only `observed` states facts, and each fact cites a FindingRef. |
| Config | `config.toml` holds defaults, environment variables override them, and secrets come from `.env` only. Tunables: retries, confidence threshold, match margin and threshold, load, job and test timeouts, model roles, cloud flag and limits. |
| Logging | Structured JSON lines to stdout per container, with `session_id` and `job_id` when known. Page content and secrets are never logged. |
| Errors | The AD-14 envelope. Inspection failure kinds are an enum: `unreachable`, `timeout`, `login_required`, `partial`. |

## Stack

| Name | Version |
| --- | --- |
| Python | 3.12 (Ubuntu 24.04 system Python in the Runner image) |
| uv | 0.13.9 |
| FastAPI | 0.165.0 |
| Pydantic | 2.14.4 |
| Uvicorn | 0.54.0 (1 worker) |
| sse-starlette | 3.7.0 |
| httpx | 0.28.1 |
| ollama (Python client) | 0.6.3 |
| Ollama runtime | 0.40.16 |
| Model | qwen3:4b-instruct-2507-q4_K_M |
| Playwright (Python) | 1.65.2 |
| Runner base image | mcr.microsoft.com/playwright/python:v1.65.2-noble |
| pytest-playwright | 0.10.0 |
| ruff | 0.17.6 |
| Node.js | 26.13.1 LTS |
| React | 19.3.1 |
| Vite | 8.3.8 |
| TypeScript (app) | 7.0.2 |
| TypeScript (type generation only) | 5.9.3 |
| openapi-typescript | 7.13.0 |
| @tanstack/react-query | 5.108.2 |
| UI styling | plain CSS, no component library |

## Structural Seed

### System and data flow

```mermaid
flowchart LR
  T((Tester)) --> UI[React UI]
  UI -- REST /api/v1 + If-Match --> BE[FastAPI backend, 1 worker]
  BE -- typed SSE --> UI
  UI -. noVNC iframe 127.0.0.1:6080 .-> RN
  BE -- model_client --> OL[(Ollama on host :11434)]
  BE -- runner_client, internal network --> RN[Runner container]
  RN -- G0 origins only --> SITE[(Target website)]
  BE -- tests/job_id + manifest --> EXV[(exchange volume)]
  RN -- out/job_id + DONE --> EXV
  BE -- store --> DATA[(data/)]
```

### Workflow and gates

```mermaid
flowchart LR
  G0{{G0 origin}} --> INS[Inspection] --> SC[Goal + Scope + Clarify] --> SUM[Scope summary]
  SC --> TP[Test plan vN] --> G1{{G1}} --> CODE[Code vN] --> VAL[ast + ruff + allowlist + locator check] --> G2{{G2}} --> G3{{G3}} --> RUN[Run]
  RUN --> FB[Feedback] --> TP
  RUN --> G4{{G4 rerun}} --> RUN
  RESCAN[Tester requests rescan: new Inspection] --> CMP[Fingerprint scoring] --> AMB{ambiguous?}
  AMB -- yes --> CLR[Clarification request] --> CMP
  AMB -- no --> REP[Repair vN + evidence] --> G5{{G5}} --> CODE2[Code vN+1: locators only] --> VAL
```

### Core entities

```mermaid
erDiagram
  SESSION ||--o{ INSPECTION : has
  SESSION ||--o{ APPROVAL : records
  SESSION ||--o{ CLARIFICATION : holds
  SESSION ||--o{ ASSISTANT_RESPONSE : has
  ASSISTANT_RESPONSE ||--|{ MODEL_CALL : attempts
  INSPECTION ||--|{ FINDING : contains
  FINDING ||--|{ LOCATOR_CANDIDATE : has
  SESSION ||--o{ TEST_PLAN : has
  TEST_PLAN ||--|{ TEST_PLAN_VERSION : versions
  TEST_PLAN_VERSION ||--|{ TEST_CASE : embeds
  TEST_PLAN_VERSION }o--|| INSPECTION : derived_from
  TEST_CODE ||--|{ TEST_CODE_VERSION : versions
  TEST_CODE_VERSION }o--|| TEST_PLAN_VERSION : derived_from
  TEST_CODE_VERSION ||--o{ RUN : executed_as
  RUN ||--o{ FEEDBACK : receives
  REPAIR }o--|| INSPECTION : old_and_new
  REPAIR ||--|| TEST_CODE_VERSION : produces
```

### Data layout

```text
data/
  sessions/{ses}/session.json          # goal history, scope, filters, clarification, confidence, rev
  sessions/{ses}/approvals.jsonl       # all gates incl. G0 origins
  sessions/{ses}/responses/{resp}.json # validated assistant responses
  inspections/{ins}/inspection.json    # findings, locators, urls, captured_at, terminal status
  inspections/{ins}/screenshot.png, crops/
  artifacts/test_plan/{tp}/v{n}.json
  artifacts/test_code/{code}/v{n}.json
  artifacts/repair/{rep}/v{n}.json
  runs/{run}/run.json, feedback.jsonl, screenshots/, trace.zip
  usage/model_calls.jsonl
```

### Source tree

```text
contracts/            # shared Pydantic models, render_locator, SSE event union (pip-installable)
backend/app/
  main.py
  utils/              # store, gates, model_client, runner_client, agent_loop, prompting, confidence, events, config
  v1/                 # inspection, session, assistant, test_design, codegen, execution, maintenance, versions, usage
runner/
  app/                # api, queue, extract.py, locators.py, conftest.py, run_tests.py, display (Xvfb/noVNC)
  Dockerfile
frontend/src/
  api/                # generated types + TanStack Query hooks
  features/           # same names as backend v1 folders
docs/                 # design document, resources.md, benchmark results
docker-compose.yml
config.toml
.env.example
```

### Deployment

```mermaid
flowchart TB
  subgraph Host["Tester laptop: Linux / macOS / Windows"]
    OL[Ollama native, GPU, bridge-bound on Linux]
    subgraph Compose["docker compose, ports on 127.0.0.1"]
      FE[frontend]
      BE[backend]
      RN[runner, hardened]
    end
    VOL[(data/ bind mount)]
    EXV[(exchange volume)]
  end
  BE --> OL
  BE --> VOL
  BE --> EXV
  RN --> EXV
  FE --> BE
```

## Capability → Architecture Map

| Capability / Area | Lives in | Governed by |
| --- | --- | --- |
| FR-1–FR-7 Inspection, locators, failures, manual login | `runner/app`, `v1/inspection` | AD-11, AD-13, AD-15, AD-19, AD-20 |
| FR-8 Persist and export Inspection | `v1/inspection`, `utils/store` | AD-3, AD-4 |
| FR-9 Multi-page (stretch) | `v1/inspection`, `v1/session` | AD-15, AD-20 |
| FR-10–FR-13 Goal, Scope, filters, clarification | `v1/session`, `utils/confidence` | AD-10, AD-16, AD-20 |
| FR-14–FR-17 Grounded summary | `v1/assistant`, `utils/agent_loop` | AD-7, AD-10 |
| FR-18–FR-21 Usage records, badge, export, averages | `utils/model_client`, `v1/usage` | AD-9, AD-18 |
| FR-22–FR-26 Design document | `docs/` | this spine, AD-21 (`resources.md`) |
| P2-TestDesign | `v1/test_design` | AD-5, AD-6, AD-7, AD-12 |
| P2-Codegen | `v1/codegen` | AD-12, AD-13, AD-17 |
| P2-Execution | `v1/execution`, `runner/app` | AD-6, AD-17, AD-18, AD-19, AD-20 |
| P2-Maintenance | `v1/maintenance` | AD-6 (G5), AD-11, AD-17 |
| P2-Versioning | `v1/versions`, `utils/store` | AD-4, AD-5 |

## Deferred

| Item | Why it can wait / revisit when |
| --- | --- |
| Credentials for tests on login-protected pages | User deferred. AD-20 already fixes how any mechanism enters (Runner conftest) and that nothing is persisted. Pick the mechanism in Phase 2 execution design, once the instructor site is known. |
| Network-level egress filtering for the Runner | Browser traffic is limited by route allowlists, and Python sockets by the AST allowlist (AD-13). Add container egress rules only if the code defense asks for it. |
| Embeddings as an extra matching signal | Only if fingerprint scoring misses renamed labels in the Phase 2 benchmark. |
| Confidence weights and threshold, match margin and threshold, timeouts, NFR-3 latency target | Tuned during development and from the benchmark. The keys already exist in config. |
| FR-9 exploration mechanics | PRD open question. AD-15 and AD-20 already cover the origin rules. |
| Frontend internal state beyond TanStack Query | Local component state is enough until shown otherwise. |
| Automated tests for the assistant itself (pytest, Vitest) | Team convention, chosen at setup. It doesn't affect how units fit together. |
| CI and hosting | Out of scope: a local, single-tester system (PRD §6). |
| Bonus feature | Candidate: the noVNC live view embedded next to Findings. Decided after Phase 1. |
