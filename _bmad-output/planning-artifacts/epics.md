---
status: final
stepsCompleted: [1, 2, 3, 4]
scope: 'Phase 1 only (Week 9)'
inputDocuments:
  - GenAI_Fall26_project.md
  - _bmad-output/planning-artifacts/prds/prd-Test-Tpt-2026-11-20/prd.md
  - _bmad-output/planning-artifacts/prds/prd-Test-Tpt-2026-11-20/addendum.md
  - _bmad-output/planning-artifacts/architecture/architecture-Test-Tpt-2026-11-20/ARCHITECTURE-SPINE.md
  - docs/design-document.md
---

# Test-Tpt: Epic Breakdown (Phase 1)

## Overview

This document breaks the **Phase 1 (Week 9)** scope of the Human-in-the-Loop Web Testing Assistant into implementable stories. It is based on the PRD, the architecture spine (AD-1 to AD-21) and the course brief. Phase 2 (test design, code generation, execution, maintenance, versioning) is out of scope, but every story must respect the spine so that Phase 2 builds on the same foundation. No UX document exists: the UI rules come from the PRD's FR-3, FR-4 and FR-11.

Self-checks (the user asked for no confirmation stops): each step was checked against `GenAI_Fall26_project.md`. The Phase 1 rubric is Architecture 4, Inspection 3, Interaction 2 and Feasibility 1. The submission items are the design doc, runnable source with setup and model config, a demo, a sample structured inspection output, and model usage/timing evidence.

## Requirements Inventory

### Functional Requirements

FR1: The tester enters a URL and starts an Inspection. The Runner opens a visible browser on it. A malformed URL is rejected before any launch. The requested URL, the final URL after redirects, and the capture time are recorded.
FR2: Every interactive element (input, textarea, select, button, link, checkbox, radio, interactive ARIA role) is extracted as a Finding with: tag, type, accessible name/label, visible text, exact DOM attributes (id, name, type, placeholder, required, disabled, pattern, min/maxlength, aria-*, data-testid), visibility, position, and containing landmark or form. Extraction is deterministic code. The ID is stable and unique within the Inspection.
FR3: A full-page screenshot with numbered markers and a Findings table (number, name, type, status) map one-to-one. Status covers at least Detected, Hidden and Inaccessible. Selecting a row highlights its marker.
FR4: The detail panel shows name/type, a screenshot crop, the DOM snippet, every observed attribute, visibility, and the locator candidates. Validation rules appear only when observed as attributes. Assistant suggestions are marked as assistant output.
FR5: Several locator candidates per Finding, ranked role/label > test id > CSS. XPath and positional selectors are never generated automatically. Candidates use Playwright Python syntax and show their live match count and a High/Medium/Low reliability. Any candidate that doesn't match exactly one element is ranked down and flagged. The best one is shown prominently, alternatives expand, and any of them can be copied.
FR6: Distinct failure states: unreachable (with possible causes), timeout (configurable, with progress shown), login required, and partial (inspected vs inaccessible counts and the reason). Never an empty screen with no reason, never an invented Finding, and retry is always available.
FR7: The tester signs in by hand in the visible Runner browser and re-runs the Inspection in the same browser session. The system never asks for or stores credentials.
FR8: Every completed or partial Inspection (Findings and screenshot) is persisted, reopens identically after a restart, keeps its source URL and capture time, and can be exported as structured JSON.
FR10: Free-text Testing goal, always visible and editable at any time. Editing it keeps the Scope. Earlier goals are kept and can be viewed.
FR11: Selecting a Findings row toggles it in the Scope. Each selected Finding gets a unique colour from a fixed high-contrast palette, shared by its row highlight and its screenshot outline. Beyond the palette size, colours are reused but the number is shown, so pairing never relies on colour alone. A counter and a Scope side panel are shown.
FR12: Group filters (container, element type, visibility, interaction, semantic role, exclusion) combine with AND, with a live match count. Individual Findings can be removed afterwards. Filters never add unobserved elements.
FR13: A goal that is vague or doesn't match anything triggers a multi-turn clarification conversation. Every question references Session context (Findings, containers, earlier goals, Scope, filters, answers) and is never repeated. Confidence against a threshold is always visible. "Test this page" offers the page's real areas. A missing element gets a Grounded statement that it wasn't observed, plus a question. Skip is an explicit action, after which suggestions come only from the Scope and are labelled as suggestions. The conversation is stored with the Session.
FR14: Summarize the current Scope in light of the goal (what was selected, what can be tested, what needs clarification), using only the Findings in Scope, the goal and the Session context. If the goal isn't actionable yet, clarify first.
FR15: Responses use the sections Observed, Inferred meaning, Unverified and Next step, written in natural language. Empty sections are omitted.
FR16: Every mention of a Finding links to it: clicking opens the detail panel and highlights it. There are no dangling links.
FR17: Validate (structure, Finding IDs in Scope, exact attribute values), then retry with the errors fed back (capped and configurable), then block what still fails with a "withheld" notice. The outcome is recorded and visible. Unsupported claims are never shown as valid.
FR18: One Model call record per call, retries included: model and version, hardware/API setup, prompt, completion and total tokens, response time, timestamp, session, response, and validation outcome. Token counts come from the runtime.
FR19: Each response has a usage badge (model, number of calls, total tokens, total time) that expands to show each call.
FR20: Model call records export as valid JSON with every FR18 field for the selected Session.
FR22: The design document has a component diagram and a data flow covering the web interface, model integration, the store and the isolated Runner.
FR23: The design document names every approval gate and where it sits.
FR24: The design document describes every validation step.
FR25: The design document shows the path from inspection to generation, execution and maintenance.
FR26: The design document records the model, its configuration, the hardware and practical resource limits.

*Stretch, excluded from Phase 1 stories: FR9 multi-page exploration, FR21 session average, model-suggested goals, selecting by clicking screenshot markers.*

### NonFunctional Requirements

NFR1: Grounding. No assistant content reaches the tester unless it has passed validation.
NFR2: Local resources. The system runs on an RTX 3060 6 GB laptop with 14 GB RAM. Prompts fit an ~8k context, and history and Findings are condensed or selected to fit.
NFR3: Responsiveness. A target is set after the Phase 1 benchmark.
NFR4: Free and secret-free. No paid model APIs or subscriptions. No secrets in the repository or the submission.
NFR5: Reproducible setup. Dependencies, setup steps and model config let another machine run the system.
NFR6: No agent frameworks. The agent loop is hand-written, with no CrewAI, LangChain or similar.

### Additional Requirements

- **No starter template.** Story 1.1 creates the repository skeleton by hand, following the spine's source tree: `contracts/`, `backend/app/{utils,v1}`, `runner/`, `frontend/` (scaffolded with create-vite react-ts), `docs/`, `docker-compose.yml`, `config.toml`, `.env.example` (AD-1, AD-3).
- **Shared `contracts/` package** installed in the backend and Runner images. It holds every stored or boundary Pydantic model (Session, Inspection, Finding, LocatorCandidate, FindingRef, Approval, ModelCallRecord, AssistantResponse, the SSE event union) and `render_locator()` (AD-3, AD-11).
- **Single gateways:** `utils/store.py` (write_once, update_json with rev/If-Match, append_jsonl, append_version; atomic and locked; the ownership table), `utils/gates.py` (record, require, approved_origins), `utils/model_client.py` and `utils/runner_client.py`. The backend never imports Playwright. One uvicorn worker (AD-2, AD-4, AD-5, AD-6).
- **G0 approval:** starting an Inspection records G0 for the origin. The Runner aborts requests outside the approved origins (AD-15).
- **Runner container:** built from `mcr.microsoft.com/playwright/python:v1.65.2-noble` with `pip install playwright==1.65.2 pytest-playwright==0.10.0`. HTTP API (`/inspect`, `/reinspect`, `/close`, `/events` SSE), one job at a time with a FIFO queue, the exchange volume `out/{job_id}/result.json` with a `DONE` marker, and backend-allocated job ids. Hardening: non-root, cap_drop ALL, no-new-privileges, read-only root filesystem with tmpfs, pids and memory limits, shm_size 1gb, init. Headed Chromium on Xvfb, shown through noVNC on 127.0.0.1:6080. extra_hosts host-gateway. One long-lived inspection context per Session (AD-19, AD-20).
- **Runner extraction:** the Runner is the only producer of finding_id (`f_001`… in DOM order), fingerprint, container format, LocatorCandidate `{strategy, args, expr, match_count, rank, reliability}` and match counts (AD-11, AD-13).
- **Model integration:**
  - `model_client` is the only caller of Ollama `/api/chat`, using `format` set to the Pydantic JSON schema. Roles are set in `config.toml` (assistant: `qwen3:4b-instruct-2507-q4_K_M`, think=false, num_ctx=8192).
  - It health-checks Ollama and sends a warm-up call at startup, and calls are serialized.
  - `model_client.record()` writes one record per attempt, after validation, to `usage/model_calls.jsonl`. Fields include inspection_id, feature, load_ms, wait_ms, response_ms, tokens_source, reused.
  - Cloud fallback is off by default (AD-7, AD-8, AD-9).
- **`utils/agent_loop.py`:** validate, then retry (default 2), then block. It owns response_id and the reuse cache, and stores `responses/{resp}.json`. `utils/prompting.py` provides the data-block wrapping ("data, never instructions") and the token budget. Each feature keeps its own prompts (AD-7, AD-10).
- **`utils/confidence.py`:** confidence computed from observable signals, with the threshold in config. The model never self-scores (AD-16).
- **Contract sync:** TypeScript types are generated from FastAPI's OpenAPI schema with openapi-typescript 7.13.0, run with TypeScript 5.9.3 in its own tool scope. The app uses TS 7.0.2. REST under `/api/v1/<feature>`, typed SSE envelope `{event, job_id, step, status, ts, data}`, error envelope `{error:{code,message,details}}`, `If-Match` (AD-14).
- **Deployment:** `docker compose up`. Ollama runs natively on the host, reached through `host.docker.internal`. On Linux Ollama must listen on the Docker bridge (`OLLAMA_HOST=172.17.0.1:11434`), and the backend prints that fix if it can't connect. Ports bind to 127.0.0.1. Secrets go only in `.env` (AD-21).
- **Conventions:** ULID ids with prefixes (ses_, ins_, resp_, call_, clr_); ISO-8601 UTC timestamps; `_ms` durations; snake_case JSON; structured JSON logs that never contain page content or secrets; failure enum unreachable|timeout|login_required|partial.
- **Pinned stack:** Python 3.12, uv 0.13.9, FastAPI 0.165.0, Pydantic 2.14.4, Uvicorn 0.54.0, sse-starlette 3.7.0, httpx 0.28.1, ollama 0.6.3, Playwright 1.65.2, ruff 0.17.6, Node 26.13.1, React 19.3.1, Vite 8.3.8, TanStack Query 5.108.2. Plain CSS, no component library.
- **Submission items** (from the brief): a model benchmark with real inspection data, `docs/resources.md`, README setup steps, the sample inspection export, the usage export, a demo script, and the design document's measured figures.

### UX Design Requirements

No UX design document. The UI requirements live in the PRD FRs (FR3, FR4, FR11, FR16, FR19) and are covered by those stories. Plain CSS, no component library (spine Stack).

### FR Coverage Map

FR1: Epic 1 (Story 1.4): start an Inspection from a URL in a visible browser
FR2: Epic 1 (Story 1.5): deterministic extraction of Findings
FR3: Epic 1 (Story 1.8): linked numbered screenshot and Findings table
FR4: Epic 1 (Story 1.9): Finding detail panel
FR5: Epic 1 (Story 1.6): ranked, verified locator candidates
FR6: Epic 1 (Story 1.10): distinct failure states and retry
FR7: Epic 1 (Story 1.11): manual login, then re-inspect
FR8: Epic 1 (Story 1.7): persist, reopen and export an Inspection
FR10: Epic 2 (Story 2.1): Testing goal with history
FR11: Epic 2 (Story 2.2): selection into Scope with colour pairing
FR12: Epic 2 (Story 2.3): combinable group filters
FR13: Epic 3 (Story 3.4): clarification conversation with computed confidence
FR14: Epic 3 (Story 3.3): Scope summary
FR15: Epic 3 (Story 3.3): structured response sections
FR16: Epic 3 (Story 3.3): clickable evidence links
FR17: Epic 3 (Story 3.2): validate, retry, block
FR18: Epic 3 (Story 3.1): Model call records
FR19: Epic 3 (Story 3.5): usage badge
FR20: Epic 3 (Story 3.5): usage JSON export
FR22–FR26: Epic 4 (Story 4.2): design document completed with measured figures
NFR1: Stories 3.2 and 3.3 · NFR2: Stories 3.1, 3.2 and 4.1 · NFR3: Story 4.1 · NFR4: Stories 1.1 and 3.1 · NFR5: Stories 1.1 and 4.2 · NFR6: Story 3.2

## Epic List

### Epic 1: Inspect a page and see what is really there
The tester runs the system with one command, enters a URL, watches a visible browser open the page, and gets a stored, exportable Inspection: numbered screenshot, Findings table, detail panel, verified locators and honest failure states, including manual login and re-inspection.
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8 (plus the foundation: AD-1–AD-6, AD-11, AD-14, AD-15, AD-19–AD-21)

### Epic 2: Steer the inspection with a goal and a Scope
The tester states and edits a Testing goal (with history) and builds a Scope by selecting Findings and combining filters, with colour-paired highlights between the table and the screenshot. No model is needed.
**FRs covered:** FR10, FR11, FR12

### Epic 3: Ask a grounded assistant and see what every answer cost
The tester asks for a Scope summary. The assistant clarifies vague goals in a context-aware conversation, answers in Observed / Inferred meaning / Unverified / Next step with clickable evidence, withholds anything it can't back up, and shows per-call tokens and time, exportable as JSON.
**FRs covered:** FR13, FR14, FR15, FR16, FR17, FR18, FR19, FR20

### Epic 4: Prove feasibility and package the Phase 1 submission
The team produces measured model evidence on real inspection data, documents resources and setup so another machine can run the system, and completes the submission items the brief lists.
**FRs covered:** FR22, FR23, FR24, FR25, FR26 (plus NFR3 and NFR5, and the brief's submission items)

**Dependencies:** Epic 2 uses Epic 1's Inspection. Epic 3 uses Epics 1 and 2 (Scope). Epic 4 uses everything. No epic needs a later one.

**Parallel build lanes (for multi-agent implementation):** once Story 1.1 lands, the stories split into three lanes that touch disjoint folders:
- **Runner:** 1.2, 1.4 (Runner side), 1.5, 1.6, 1.11 (`runner/`)
- **Backend:** 1.4 (backend side), 1.7, 1.10, 2.1, 3.1, 3.2 (`backend/app/`)
- **Frontend:** 1.3, 1.8, 1.9, 2.2, 2.3, 3.5 (`frontend/`)

`contracts/` is changed only in Story 1.1 and in stories that state it explicitly.

## Epic 1: Inspect a page and see what is really there

The tester runs the system with one command, enters a URL, watches a visible browser open the page, and gets a stored, exportable Inspection with linked views, verified locators and honest failure states.

### Story 1.1: One-command project skeleton with shared contracts and storage

As a team member,
I want the repository skeleton, the shared contracts and the storage/approval helpers to exist and start with one command,
So that every later story builds on the same shapes, gateways and conventions instead of inventing its own.

**Acceptance Criteria:**

**Given** a fresh clone with Docker and Node installed
**When** I run `docker compose up --build`
**Then** the `backend` (FastAPI, 1 uvicorn worker) and `frontend` (Vite React-TS dev server) services start, and `GET /api/v1/health` returns `{"status":"ok"}`
**And** published ports bind to `127.0.0.1` only

**Given** the `contracts/` package
**When** it is installed in the backend image (`pip install -e contracts` or equivalent)
**Then** it defines the Pydantic models Session, Inspection, Finding, LocatorCandidate, FindingRef, Approval, ModelCallRecord, AssistantResponse and the SSE event envelope/union, with the fields in spine AD-3, AD-9 and AD-11, plus `render_locator()` producing Playwright Python syntax
**And** there are unit tests for the model round-trip (JSON in and out) and for `render_locator()` on role, label, test_id, css and text strategies

**Given** `backend/app/utils/store.py`
**When** a feature writes through `write_once`, `update_json(path, fn, expected_rev)` or `append_jsonl`
**Then** writes are atomic (temp file, fsync, rename) and locked per path; `write_once` fails on an existing file; `update_json` with a stale rev raises a conflict that the API maps to HTTP 409
**And** unit tests cover each mode, including two concurrent `append_jsonl` calls that don't interleave

**Given** `backend/app/utils/gates.py`
**When** `gates.record(G0, session, origin)` is called
**Then** an Approval line is appended to `sessions/{ses}/approvals.jsonl`, and `gates.approved_origins(session)` returns it
**And** `gates.require("runner.load_url", session, url)` raises for an unapproved origin

**Given** the repository root
**When** I list it
**Then** it contains `contracts/`, `backend/app/{utils,v1}/`, `runner/`, `frontend/`, `docs/`, `docker-compose.yml`, `config.toml`, `.env.example` and `.gitignore` (which ignores `.env` and `data/`), with no secrets committed
**And** the frontend has an `npm run gen:types` script that runs openapi-typescript 7.13.0 with TypeScript 5.9.3 against the backend's `/openapi.json` into `frontend/src/api/schema.d.ts`

### Story 1.2: Isolated Runner container with a visible browser

As a tester,
I want the browser to run inside an isolated, hardened container that I can still watch and use,
So that the assistant can open pages safely while I see exactly what it sees.

**Acceptance Criteria:**

**Given** `runner/Dockerfile`
**When** it is built
**Then** it starts `FROM mcr.microsoft.com/playwright/python:v1.65.2-noble`, installs `playwright==1.65.2` and `pytest-playwright==0.10.0` and the `contracts` package, plus Xvfb, x11vnc, websockify and noVNC, and runs as a non-root user

**Given** `docker compose up`
**When** the `runner` service starts
**Then** it runs with `cap_drop: [ALL]`, `no-new-privileges`, a read-only root filesystem with tmpfs where needed, `pids_limit`, `mem_limit`, `shm_size: 1gb`, `init: true`, `extra_hosts: host.docker.internal:host-gateway`, no host bind mounts except the exchange volume, and no docker.sock
**And** its HTTP API is reachable only on the internal compose network, while noVNC is published on `127.0.0.1:6080`

**Given** the Runner API
**When** `GET /health` is called from the backend container
**Then** it returns ok, and `GET /events` streams SSE using the contracts envelope
**And** jobs run one at a time from a FIFO queue, each with a configurable timeout

**Given** a browser view is opened at `http://127.0.0.1:6080`
**When** the Runner launches headed Chromium on Xvfb
**Then** the tester can see the browser and click and type in it

### Story 1.3: Frontend shell with live browser view and typed API client

As a tester,
I want one screen that shows the workbench next to the live Runner browser,
So that I can follow the inspection without switching windows.

**Acceptance Criteria:**

**Given** the frontend (React 19, Vite 8, TanStack Query, plain CSS)
**When** I open `http://127.0.0.1:5173`
**Then** I see a layout with a URL bar, an area for the Findings and screenshot, a side panel, and an embedded noVNC view of the Runner (iframe to `127.0.0.1:6080`) that can be collapsed
**And** the backend health is shown as connected or not connected

**Given** the generated `schema.d.ts`
**When** the frontend calls the API
**Then** all request and response types come from the generated file (no hand-written duplicates), through a small typed fetch wrapper and TanStack Query hooks in `frontend/src/api/`
**And** a reusable SSE hook parses the contracts event envelope

### Story 1.4: Start an Inspection from a URL

As a tester,
I want to enter a URL and start an Inspection that opens the page in the visible browser,
So that I can begin analysing a real page.

**Acceptance Criteria:**

**Given** the URL bar
**When** I enter a malformed URL (not http/https, or unparsable)
**Then** I get a validation message, and no Session, approval or Runner job is created

**Given** a valid URL
**When** I click "Start inspection"
**Then** the backend creates a Session (`ses_` id) if there isn't one, records G0 for the URL's origin through `gates.record`, allocates an `ins_` id, and calls `runner_client.inspect` with that id as `job_id` and the approved origins
**And** the visible Runner browser loads the page, with progress shown in the UI over SSE

**Given** the page loads
**When** the Runner finishes the job
**Then** `out/{job_id}/result.json` contains the requested URL, final URL after redirects, capture time (ISO-8601 UTC) and a full-page screenshot, and the `DONE` marker is written last
**And** the Runner's inspection context aborts requests to origins outside the approved list

**Given** the backend sees `DONE`
**When** it imports the result
**Then** `v1/inspection` exposes it as the Session's current Inspection through `GET /api/v1/inspection/current`

### Story 1.5: Extract interactive elements as Findings

As a tester,
I want every interactive element on the page extracted with its real attributes,
So that I see what the page actually contains instead of guessing.

**Acceptance Criteria:**

**Given** a loaded page in the Runner
**When** `runner/app/extract.py` runs
**Then** it returns one Finding per input, textarea, select, button, link, checkbox, radio and element with an interactive ARIA role, using deterministic DOM code only (no model)
**And** each Finding has `finding_id` `f_001`… in DOM order, tag, type, accessible name/label, visible text, the attributes present (id, name, type, placeholder, required, disabled, pattern, minlength, maxlength, aria-*, data-testid) with values exactly as in the DOM, visibility state (visible / hidden / inaccessible), bounding box, `container` in one format (`form#login`, `form[name=x]`, `nav`, `main`…), and a `fingerprint` per AD-11

**Given** a test fixture HTML page with a login form, a hidden input, a disabled button and links
**When** the extraction tests run
**Then** the counts, attributes, containers and visibility match the fixture exactly, and running twice gives identical output

### Story 1.6: Ranked, verified locator candidates

As a tester,
I want several locators for each Finding, ranked by reliability and checked against the live page,
So that I can trust and copy the best one.

**Acceptance Criteria:**

**Given** a Finding
**When** `runner/app/locators.py` generates candidates
**Then** it produces LocatorCandidates `{strategy, args, expr, match_count, rank, reliability}` in the order role/accessible-name, label, test_id, then CSS (attribute-based), with `expr` from `contracts.render_locator()` in Playwright Python syntax (e.g. `page.get_by_role("button", name="Sign In")`)
**And** XPath and positional selectors (nth-child, index) are never generated

**Given** each candidate
**When** it is verified on the live page
**Then** `match_count` is the real count, any candidate whose count isn't exactly 1 is ranked below every unique candidate and flagged, and reliability is High/Medium/Low by strategy and uniqueness
**And** a fixture test with two identical "Submit" buttons shows the role candidate flagged as non-unique and a unique candidate (test id or CSS) ranked first

### Story 1.7: Persist, reopen and export Inspections

As a tester,
I want every Inspection saved so I can reopen it after a restart and export it as JSON,
So that later steps refer to what was actually observed and I can submit a sample output.

**Acceptance Criteria:**

**Given** an Inspection imported from the Runner (complete or partial)
**When** `v1/inspection` stores it
**Then** it is written once through `store.write_once` to `inspections/{ins}/inspection.json` with its screenshot and crops, in a terminal status, and is never changed afterwards

**Given** the backend restarts
**When** I open `GET /api/v1/inspection/{ins}` or the Session's list of Inspections
**Then** the Findings, locators and screenshot are identical to the original

**Given** a stored Inspection
**When** I click "Export JSON"
**Then** I download valid JSON matching the contracts Inspection schema, including the source URL, final URL and capture time
**And** a copy can be saved to `docs/samples/inspection.json` for the submission

### Story 1.8: Linked numbered screenshot and Findings table

As a tester,
I want a screenshot with numbered markers next to a table that uses the same numbers,
So that I can match each row to its element at a glance.

**Acceptance Criteria:**

**Given** a stored Inspection
**When** the results view renders
**Then** the full-page screenshot shows a numbered marker at each Finding's bounding box, and the Findings table lists number, element name, type and status (Detected / Hidden / Inaccessible)
**And** marker numbers and row numbers correspond one-to-one

**Given** the table
**When** I select a row
**Then** its marker on the screenshot is highlighted and scrolled into view

### Story 1.9: Finding detail panel

As a tester,
I want to open any Finding and see everything observed about it,
So that I can understand the element without reading the page source.

**Acceptance Criteria:**

**Given** a Finding row
**When** I open its detail panel
**Then** it shows name and type, a screenshot crop with the element highlighted, its DOM/HTML snippet, all observed attributes, visibility, and the locator candidates (best one prominent, alternatives expandable, each with match count and reliability, each copyable)
**And** validation rules appear only when observed as attributes (required, type=email, pattern, maxlength…); behaviour that wasn't observed is never claimed
**And** the panel has a separate, clearly labelled "Assistant" area, kept apart from observed evidence and empty in this story

### Story 1.10: Distinct failure states with retry

As a tester,
I want to know exactly why an Inspection failed and what was still captured,
So that I am never left with an empty or silent screen.

**Acceptance Criteria:**

**Given** an unreachable URL
**When** the Inspection runs
**Then** I see "unreachable" with possible causes (DNS, connection refused, wrong port), and no Findings are invented

**Given** a page that loads slower than the configured timeout (config `inspection.load_timeout_ms`)
**When** the timeout passes
**Then** progress is shown during loading, and then a "timeout" state appears along with whatever was captured

**Given** a page that redirects to a login form or shows one in place of the content
**When** the Inspection completes
**Then** the status is "login_required", with a message that the page needs a login and that the tester can sign in by hand in the visible browser

**Given** some elements can't be inspected
**When** the Inspection completes
**Then** the status is "partial", with inspected vs inaccessible counts, the reason, and the captured Findings
**And** every failed or partial Inspection has a Retry action that creates a new Inspection

### Story 1.11: Manual login, then re-inspect in the same session

As a tester,
I want to sign in by hand in the visible browser and then inspect again,
So that I can analyse pages behind a login without giving the assistant my credentials.

**Acceptance Criteria:**

**Given** an Inspection with status login_required
**When** I sign in by hand in the noVNC browser view and click "Re-inspect"
**Then** `runner_client.reinspect` reuses the Session's long-lived inspection context, and a new Inspection captures the elements that were inaccessible before
**And** the new Inspection is stored separately; the earlier one is unchanged

**Given** the whole flow
**When** I check requests, logs and `data/`
**Then** the system never asks for, logs or stores credentials

## Epic 2: Steer the inspection with a goal and a Scope

The tester states what to do (Testing goal) and with which elements (Scope), with colour-paired highlights and combinable filters. No model is involved.

### Story 2.1: Testing goal with history

As a tester,
I want to write and edit a Testing goal at any time and see my earlier goals,
So that the assistant always knows what I'm trying to test.

**Acceptance Criteria:**

**Given** a Session with an Inspection
**When** I write a goal and save it
**Then** `v1/session` stores it in `session.json` through `store.update_json` with `If-Match: <rev>`, and the current goal is always visible next to the Findings

**Given** an existing goal
**When** I edit it
**Then** the Scope stays the same, the earlier goal is kept in a viewable goal history (text and timestamp), and later assistant requests use the new goal
**And** a stale rev returns 409, and the UI reloads and asks me to retry

### Story 2.2: Select Findings into Scope with colour pairing

As a tester,
I want to click rows to add or remove Findings from my Scope, with matching colours on the screenshot,
So that I can see exactly which elements the assistant will use.

**Acceptance Criteria:**

**Given** the Findings table
**When** I click a row
**Then** the Finding toggles in or out of the Scope, stored in `session.json` as FindingRefs bound to this Inspection

**Given** several selected Findings
**When** they render
**Then** each gets a unique colour from a fixed high-contrast palette, used for both its row highlight and its screenshot outline, all distinct from each other and from the unselected marker style
**And** beyond the palette size colours are reused, always with the Finding number shown

**Given** a non-empty Scope
**When** I look at the page
**Then** a counter shows "N elements selected" and a side panel lists the Findings in Scope with their key details

### Story 2.3: Combinable group filters

As a tester,
I want to narrow the Scope with filters and then remove individual items,
So that I can focus quickly on, say, the inputs in the login form.

**Acceptance Criteria:**

**Given** filters for container, element type, visibility (include or exclude hidden), interaction (only clickable), semantic role and exclusion
**When** I combine "container = form#login" and "type = input"
**Then** only inputs inside that form match (AND logic), and a live count shows the number of matches

**Given** a filtered result
**When** I apply it to the Scope and then remove one Finding
**Then** the Scope holds the filtered set minus that Finding, and the active filters are stored in the Session
**And** filters only ever select from recorded Findings, never adding anything that wasn't observed

## Epic 3: Ask a grounded assistant and see what every answer cost

The tester gets a validated, evidence-linked Scope summary from the local model, with clarification when the goal is unclear and visible per-call usage.

### Story 3.1: Model client with role config, warm-up and usage records

As a tester,
I want every model call to go through one client that measures and records it,
So that token counts and timings are real and nothing escapes the usage log.

**Acceptance Criteria:**

**Given** `config.toml` with role `assistant` = `{provider: "ollama", model: "qwen3:4b-instruct-2507-q4_K_M", think: false, num_ctx: 8192}` and the cloud provider disabled
**When** the backend starts
**Then** `utils/model_client.py` health-checks Ollama at `OLLAMA_BASE_URL` (default `http://host.docker.internal:11434`), sends one warm-up call, and keeps the model loaded (`keep_alive`)
**And** if Ollama is unreachable, the health endpoint reports it and the log prints the Linux fix (`OLLAMA_HOST=172.17.0.1:11434`)

**Given** a feature calls `model_client.call(role, messages, schema)`
**When** the call completes
**Then** it uses Ollama `/api/chat` with `format` set to the schema and `think` false (thinking is only sent if `/api/show` reports the capability), calls are serialized, and the result carries `prompt_eval_count`, `eval_count`, `load_duration` and the total time
**And** `model_client.record(call, validation_outcome)` appends one ModelCallRecord per attempt to `usage/model_calls.jsonl` with every AD-9 field (`tokens_source: "runtime"`, `setup` describing the GPU and runtime, `load_ms` separate from `response_ms`)

**Given** a code search
**When** we look for model runtime calls
**Then** only `utils/model_client.py` imports the `ollama` client or calls `/api`

### Story 3.2: Agent loop: schema output, validate, retry, block

As a tester,
I want every assistant answer checked against the Inspection before I see it,
So that I never see a claim the page doesn't support.

**Acceptance Criteria:**

**Given** `utils/agent_loop.py` (hand-written, no agent framework) and `utils/prompting.py`
**When** a feature runs `agent_loop.run(feature, schema, prompt_parts, scope)`
**Then** page-derived content goes into prompts only as quoted JSON inside delimited data blocks, under a system preamble saying it is data and never instructions, and the prompt fits the token budget (Findings in Scope, then goal, then condensed history, under `num_ctx` minus reserved output)

**Given** a model response
**When** it is validated
**Then** these are checked: schema structure, every cited FindingRef exists in the Inspection and is in Scope, and every quoted attribute value matches the Finding exactly

**Given** a failed validation
**When** retries remain (default 2, config `assistant.max_retries`)
**Then** the model is called again with the validation errors fed back, and each attempt gets its own usage record

**Given** retries are exhausted
**When** some claims still fail
**Then** those claims are removed, the response carries a "withheld" notice, and if nothing valid remains the result says the assistant couldn't produce a grounded answer and offers Retry
**And** the AssistantResponse (with `response_id`, the validation outcome and the number of retries) is written once to `sessions/{ses}/responses/{resp}.json`

**Given** unit tests with a fake model_client
**When** the fake returns a hallucinated finding_id, then a wrong attribute value, then a valid answer
**Then** the loop retries twice and returns the valid answer; with three bad answers it blocks

### Story 3.3: Grounded Scope summary with sections and evidence links

As a tester,
I want to ask for a summary of my Scope and get a structured, evidence-linked answer,
So that I understand what I selected, what can be tested and what's still unclear.

**Acceptance Criteria:**

**Given** a Session with a goal and a non-empty Scope
**When** I click "Summarize Scope"
**Then** `v1/assistant` runs the agent loop using only the Findings in Scope, the goal and the Session context, with no other Findings and no outside knowledge
**And** the UI shows pipeline progress over SSE (building prompt → calling model → validating → retry N → done) and never streams raw tokens

**Given** a validated response
**When** it is shown
**Then** it has the sections Observed, Inferred meaning, Unverified and Next step in natural language, empty sections omitted, and Observed holds only grounded statements
**And** each Finding mention is a link that opens the Finding's detail panel and highlights it in the table and screenshot, with no dangling links
**And** testing suggestions for a single Finding appear in the detail panel's "Assistant" area (Story 1.9), labelled as assistant output

### Story 3.4: Context-aware clarification conversation with computed confidence

As a tester,
I want the assistant to ask specific questions when my goal is vague or names something missing,
So that it never guesses what I mean.

**Acceptance Criteria:**

**Given** `utils/confidence.py`
**When** the goal and Scope change
**Then** confidence is computed from observable signals only (the goal references existing Findings or containers, Scope is non-empty, the goal names an action, the number of open ambiguities); `v1/session` stores `{confidence, actionable, clarification[]}` in `session.json`, and the current confidence is always shown

**Given** the goal "test this page"
**When** clarification starts
**Then** the question names the page's real areas (observed forms or containers) as options

**Given** a goal naming an element that wasn't observed (e.g. "test the search bar" on a login page)
**When** the assistant answers
**Then** it gives a grounded statement that no such element was observed, plus a clarification question, and never substitutes another element
**And** clarification turns are produced through the agent loop (Story 3.2), so they are validated and recorded like any other response

**Given** an ongoing conversation
**When** I answer
**Then** follow-up questions build on my answers, reference Session context (Findings, container, earlier goals, Scope, filters), are never generic, and never repeat an answered question, and each turn is stored with a `clr_` id
**And** when confidence reaches the threshold (config `clarification.threshold`), the assistant proceeds

**Given** the goal isn't actionable
**When** I click "Summarize Scope" (Story 3.3)
**Then** the assistant asks its clarification question first and summarizes only once confidence reaches the threshold or I skip

**Given** an open question
**When** I click Skip
**Then** the assistant generates suggestions grounded only in the Findings in Scope, labelled as suggestions (skipping never happens on a timeout)

### Story 3.5: Usage badge and usage JSON export

As a tester,
I want to see what each answer cost and export all usage,
So that I have model usage and timing evidence for the submission.

**Acceptance Criteria:**

**Given** an assistant response
**When** it is displayed
**Then** a badge shows model · number of calls · total tokens · total response time (e.g. "qwen3:4b · 2 calls · 1,250 tokens · 6.4 s"), and expanding it lists each call with its tokens, response time, load time and validation outcome
**And** model time is labelled separately from any browser time

**Given** a Session
**When** I click "Export usage"
**Then** I download valid JSON with every ModelCallRecord field for that Session, readable without the app
**And** a copy can be saved to `docs/samples/model_calls.json` for the submission

## Epic 4: Prove feasibility and package the Phase 1 submission

The team produces measured model evidence on real inspection data and completes every submission item the brief lists for Week 9.

### Story 4.1: Model benchmark on real inspection data

As the team,
I want a repeatable benchmark that runs the Scope summary on real Inspections with our model,
So that our model and resource limits rest on measured evidence.

**Acceptance Criteria:**

**Given** `backend/scripts/benchmark.py` and 10–20 Scope-summary cases built from stored Inspections
**When** it runs against `qwen3:4b-instruct-2507-q4_K_M` (the only model the project uses)
**Then** it records JSON validity on the first attempt, grounding validation pass rate, retries needed, mean and p95 response time, tokens/s and peak VRAM (from `nvidia-smi`), using the real agent loop and model_client

**Given** the results
**When** the script finishes
**Then** it writes `docs/benchmark-results.json` and a Markdown table into `docs/resources.md`, together with hardware, Ollama version, quantization, context size, cold-load time, practical limits and the free-tier rate limits documented for the optional cloud fallback
**And** an NFR3 response-time target is proposed from the measured p95

### Story 4.2: Setup documentation and Phase 1 submission package

As a TA evaluating the project,
I want clear setup steps, model configuration and sample outputs,
So that I can run the system on another machine and verify the Phase 1 rubric.

**Acceptance Criteria:**

**Given** `README.md`
**When** a new machine follows it
**Then** it covers prerequisites (Docker, Ollama), the model pull, `OLLAMA_HOST` per OS, `.env` from `.env.example`, `docker compose up`, opening the UI and noVNC, and troubleshooting (Ollama unreachable, docker group, first-call warm-up)

**Given** the submission folder
**When** it is checked against the brief's Phase 1 list
**Then** it holds `docs/design-document.md` (measured figures filled in from `docs/resources.md`), the model configuration (`config.toml`), `docs/samples/inspection.json`, `docs/samples/model_calls.json`, and `docs/demo-script.md` (open supplied page → inspect → findings → set goal and select elements → clarification → grounded summary with usage badge)
**And** no API secrets are present anywhere in the repository
