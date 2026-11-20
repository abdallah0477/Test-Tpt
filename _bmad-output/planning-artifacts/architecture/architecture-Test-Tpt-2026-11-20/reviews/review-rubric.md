---
review_of: ARCHITECTURE-SPINE.md
lens: good-spine rubric
date: 2026-11-20
verdict: revise-before-build
---

# Rubric Review: Architecture Spine (Test-Tpt, 2026-11-20)

**Verdict:** A strong, mostly enforceable spine with good coverage, but it needs one revision pass before parallel build. Three ownership and contract gaps would let independently built features diverge on day one: shared artifact schemas, who writes `session.json`, and what a "test code version" is. The operational envelope is also only partly decided.

User choices respected and not challenged: `utils/` + `v1/<feature>` with no layers, JSON-file storage, per-feature prompts.

## Rubric scorecard

| Criterion | Result | Notes |
|---|---|---|
| Fixes the real divergence points, misses none | Partial | Misses shared schema ownership, artifact-kind write ownership, the test-code source of truth, and the canonical hash. See F1–F4. |
| Every AD Rule is enforceable and prevents its divergence | Mostly | AD-2, AD-3, AD-5, AD-6, AD-8, AD-10, AD-12 and AD-14 are crisp. AD-15, AD-16 and AD-20 contradict AD-1. AD-17 cannot be checked as written. |
| Nothing under Deferred lets units diverge | Mostly | "Credentials for tests on login-protected pages" interacts with AD-20 and can diverge. See F6. |
| Covers the spec's capabilities | Mostly | Missing: storage for run feedback, test-case entity, page-level averages field, and codegen under AD-6. See F5. |
| Every initiative-altitude dimension is decided, deferred or open | Partial | Deployment is decided. Resource limits, timeouts, runner hardening, data growth, port exposure and model-call concurrency are not. See F7. |
| Mermaid diagrams valid | Pass (manual parse) | All 5 diagrams are syntactically valid. There are semantic gaps in ER and workflow. See section "Diagrams". |

## Findings

### F1 [HIGH] AD-1 / AD-14: no home for cross-feature data models (Finding, Inspection, Session, versions, approvals, Runner job results)
**Problem.** AD-1 places "Pydantic schemas" inside each feature folder and forbids `v1/X` importing `v1/Y`. But `Inspection`/`Finding`/`LocatorCandidate` are produced by `v1/inspection` and consumed by `assistant`, `session` (filters), `test_design`, `codegen` and `maintenance`. Session state is read by `assistant` and `test_design`. Under AD-1, each consumer must redefine these models, which is exactly the "artifacts that differ in shape between features" that AD-3 claims to prevent. The Runner is a separate container and package, so AD-14's "Pydantic is the single source of the contract for backend ↔ Runner" has no stated location either. Nothing says whether the Runner imports backend code, the two share a package, or the backend mirrors the Runner's models.
**Fix.** Add a Rule to AD-1 or AD-3: *"Every model stored by `store.py` or crossing the Runner boundary is defined once in `backend/app/utils/schemas/` (or a top-level `contracts/` package installed in both backend and runner images). Feature folders hold only request/response models private to their own routes."* Also add a common version envelope: `{kind, id, version, created_at, derived_from, restored_from?, content_sha256, body}`.

### F2 [HIGH] AD-15 / AD-16 / AD-20 contradict AD-1 on who writes Session state
**Problem.** AD-20 says `session.json` (approved origins, goals, scope, clarification) is "written only through `v1/session`". But:
- AD-15 says *starting an Inspection* (`v1/inspection`) records G0 for the origin on the Session, which is a cross-feature write.
- AD-5 stores approvals in `approvals.jsonl` via `utils/gates.py`, while AD-20 puts origins in `session.json`. That gives two candidate sources of truth for G0.
- AD-16 puts the confidence function in `v1/session`, but FR-14 requires `v1/assistant` to "clarify before summarizing". The assistant can't import it, so it will either re-implement confidence or skip the check.
- Clarification turns created during an assistant request have no legal writer.

**Fix.** (a) G0 is an ordinary approval record in `approvals.jsonl` written by `utils/gates.py`, and allowed origins are *derived* from approvals. Remove "approved origins" from `session.json`. (b) Move the confidence function to `utils/` (e.g. `utils/confidence.py`), or have `v1/session` persist `{confidence, actionable}` in `session.json` and make the assistant read it and refuse when `actionable == false`. (c) State that only `v1/session` routes append clarification turns. The assistant returns a "needs clarification" result and the UI routes it to the session endpoint.

### F3 [HIGH] AD-4 / AD-13 / AD-17: "test code version" and "test case" are undefined, so repair, edit and restore can diverge
**Problem.**
- AD-4 versions "test plan, test case and test code" and Conventions define `tc_`, but the data layout lists only `test_plan | test_code | repair`, and the ER diagram has no TEST_CASE.
- AD-13 makes one page object *per inspected page* (shared across test cases) plus one `test_<case>.py` per case. Is the page object part of each `test_code` version, or a separate artifact? A G5 repair to a shared page object silently changes every test that uses it.
- AD-17 says steps/assertions stay "byte-identical, checked by diffing" but doesn't say *what* is diffed: model step JSON or the rendered `.py`.
- The brief requires code review with edits, and AD-4 allows "test code edit". A hand-edited `.py` drifts from the step JSON, the generator regenerates over it, and edits can change assertions while skipping G1, which AD-17 forbids.

**Fix.** Add an AD (or extend AD-13):
- *"Source of truth for a `test_code` version is `{page_objects: {page_id: locator_map}, cases: {tc_id: steps_json}}`. The `.py` files are rendered from it."*
- *"Tester edits to code go through the same structure. Free-text edits to `.py` are either disallowed, or stored as a new version whose steps/assertions are re-parsed and must pass the AD-17 check."*
- *"G5 may change only `page_objects.*` locator expressions. `cases` must be byte-identical (canonical JSON) to the source version."*
- Add `test_case` to the data layout and ER, or explicitly state that cases live inside `test_plan` versions and drop the `tc_` versioning claim.

### F4 [MEDIUM] AD-3 / AD-4 / AD-5: version allocation and approval hashing are not deterministic
**Problem.** `v{n+1}` allocation (codegen, versions/restore, maintenance can all write `test_code`) has no serialization rule. Async handlers or more than one uvicorn worker can race to the same `n`. No rule says which feature owns writes to each artifact kind. `content_sha256` in AD-5 doesn't define what bytes are hashed, so two features computing "the same" hash differently will lock gates permanently or (worse) unlock the wrong content.
**Fix.**
- AD-3: *"Backend runs one uvicorn worker. `store.py` allocates versions under a process-wide lock and uses exclusive create (`O_EXCL`) for `v{n}.json`."*
- AD-5: *"`content_sha256` = SHA-256 of `body` serialized with `json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=False)`, computed only in `store.py`."*
- Add an ownership table (kind → writing feature), e.g. test_plan: test_design and versions (restore only); test_code: codegen, maintenance (G5) and versions (restore).

### F5 [MEDIUM] Capability coverage gaps (Phase 2 rubric and FR-18/21)
- **Page-level average** (brief: "session or page-level average"). AD-18 averages "for a page", but the AD-8 record has no `inspection_id`/`page_url`. Add `inspection_id` (nullable) to the AD-8 record.
- **User feedback on runs** (brief Execution row). The workflow shows `FB → TP`, but feedback has no artifact kind, ID prefix or storage path. Add `feedback` (`fb_`) under `runs/{run_id}/feedback.jsonl` or as an artifact kind with `derived_from: run`.
- **AD-6 does not bind P2-Codegen**, yet AD-13 asks the model for step JSON. Without binding, codegen may skip `agent_loop` validate/retry/block. Add P2-Codegen to AD-6 Binds, and require that step JSON cite only page-object members that exist.
- **FR-18 "model name and version"**: the model tag isn't the version. Record the Ollama model `digest` in `setup` or as its own field.
- **Run results schema** (pass/fail, screenshots, failure details, `browser_ms`, `test_ms`) is referenced by AD-18 but never shaped. Covered by the F1 fix if `RunResult` goes in shared schemas.

### F6 [MEDIUM] Deferred: "Credentials for tests on login-protected pages" can cause divergence
**Problem.** AD-20 forces a fresh browser context per test run, and FR-7/§6 forbid storing credentials. If the instructor site has a login-protected workflow, one teammate will reuse the inspection context's `storage_state`, another will put login steps in tests, and a third will skip the test. These options are incompatible, and the choice touches runner, codegen and execution.
**Fix.** Decide the mechanism now even if implementation waits. For example: *"The Runner may export the Session's inspection-context `storage_state` in memory only and inject it into a fresh test context when the tester approves at G3. It is never written to `data/` or the exchange volume."* Alternatively: *"Phase 2 tests run only on pages reachable without login."* Keep only the timing deferred.

### F7 [MEDIUM] Operational envelope partly undecided (resource limits, runner hardening, timeouts, data growth)
Decided: deployment (AD-19), environments (compose vs. native, same config keys), logging, secrets. Not decided, deferred or opened:
- **Runner hardening.** The brief requires "prevent unrestricted host commands" and "limit execution to the approved target". `page.route` limits only browser traffic. Generated or edited pytest code runs arbitrary Python with unrestricted container network egress, and `ruff check` doesn't block `import subprocess`. Fix: in AD-10, require a non-root user, `cap_drop: [ALL]`, `security_opt: no-new-privileges`, `read_only` rootfs except `out/` and tmp, `pids_limit`, `mem_limit`, `shm_size: 1gb` (Chromium needs it), and no Docker socket. In AD-12, add an AST import/call allowlist (pytest, playwright, generated page objects, `re`; forbid `os`, `subprocess`, `socket`, `eval`, `exec`, `open`).
- **Timeouts.** Only "load timeout" is a tunable. Add model-call timeout, runner job timeout and per-test timeout to Config, with defaults.
- **Model concurrency.** "One model loaded at a time" is stated but not enforced. Fix: `model_client` serializes calls (semaphore = 1), and setup sets `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1`.
- **Port exposure.** noVNC :6080, backend :8000 and runner API should bind `127.0.0.1` only, and the runner API should not be published to the host at all (compose-internal network).
- **Data growth.** Traces, screenshots and crops accumulate in `data/`. Add a Deferred row ("no retention; manual `data/` cleanup; revisit if disk > N GB") so it's explicit.
- **Health/startup.** The backend should check Ollama reachability and the configured model's presence at startup, and fail with a clear error. One line under AD-19.

### F8 [LOW] Minor consistency issues
- AD-17, AD-18, AD-19 and AD-20 lack the `[ADOPTED]` tag that the other ADs carry. Tag them or mark them proposed.
- AD-11's "one shared scoring function" has no location. Name it (`utils/matching.py`), since a rule-of-location is what makes "shared" enforceable.
- Stack: `uv` = "latest at setup" is unpinned. Pin a version for NFR-5. Check that `openapi-typescript` 7.x works with TypeScript 7.0 (native compiler); otherwise pin TS 5.x for the type-generation step.
- AD-6 "backend turns the validated JSON into text" vs FR-16 clickable links: specify that the rendered output keeps `finding_id` references as structured spans (e.g. `{text, finding_ids[]}`), not flattened prose.
- The env-var override naming scheme for `config.toml` (e.g. `TPT_SECTION__KEY`) is unstated. Without it, teammates will invent different names.

## Diagrams

All five mermaid blocks were checked by hand (no mermaid CLI is installed in this environment):

| Diagram | Syntax | Semantics |
|---|---|---|
| Design paradigm flowchart (subgraph-to-subgraph edge `v1 --> utils`) | Valid (mermaid ≥ 9.4) | Fine |
| System and data flow | Valid | Fine. The runner API port isn't shown, which is consistent with keeping it internal (F7). |
| Workflow and gates | Valid | `FB → TP` should show re-entry through G1. `G5 → CODE` correctly loops back through VAL/G2/G3. G0 has no explicit link to Session approval storage. |
| Core entities (erDiagram) | Valid; duplicate REPAIR–INSPECTION relations with distinct labels are allowed | Missing TEST_CASE, FEEDBACK and CLARIFICATION. TEST_CODE isn't linked to SESSION. Page object vs test code relationship is undefined (F3). |
| Deployment | Valid | Doesn't show the internal network or port bindings (F7). |

## What is solid (keep as is)

- AD-2's three single gateways (model, runner, store) are greppable and enforceable in review or CI (`grep -r "import playwright" backend/` must return nothing).
- AD-5's approvals pinned by version + hash, with gates checked server-side, directly meet the brief's explicit-approval requirement.
- AD-6 with AD-9 (schema-constrained JSON, ID-only citations, data-block quoting) is a concrete grounding and prompt-injection stance that still lets each feature own its prompts.
- AD-11 and AD-16 keep matching and confidence in code, which avoids the most common divergence (model-judged thresholds).
- AD-8's token source and reuse flags exactly cover the brief's "label estimates; distinguish reused results".
