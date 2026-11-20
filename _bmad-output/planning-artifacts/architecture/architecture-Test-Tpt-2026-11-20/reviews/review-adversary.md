# Adversarial Review: Architecture Spine (Test-Tpt, 2026-11-20)

- **Target:** `ARCHITECTURE-SPINE.md` (draft, 20 ADs)
- **Context:** `prds/prd-Test-Tpt-2026-11-20/prd.md`
- **Method:** For each shared entity or interaction, build two units one level down (`v1/<feature>`, `runner/app`, `frontend/src/features/*`). Each unit obeys every AD as written, and the two still don't fit together. Each such pair is a hole, and each hole gets a proposed new or tightened rule.
- **Constraints respected:** vertical-slice feature folders (no service or repository layers), JSON files under `data/`, prompts owned by each feature. Every fix below is a helper in `utils/`, a schema fixed in the spine, or a rule about file layout or ownership.

## Verdict

**The spine is not yet buildable by independent teams. It needs one tightening pass before Phase 1 stories start.**

The paradigm is sound and the gateways in AD-2 are well chosen. The problem is that the spine says *who may touch* `data/` without fixing *what is in it* or *how two writers serialise*. The main gaps:

1. No shared contract for Runner ↔ backend payloads (Finding, LocatorCandidate, job result).
2. No version-file envelope and no definition of `content_sha256`.
3. No concurrency rule for read-modify-write files (`session.json`) or for allocating version numbers.
4. Gate prerequisites are not chained, so each feature checks only its own gate.
5. AD-1, AD-15, AD-16 and AD-20 force cross-feature reads and writes that the spine forbids, with no permitted path.
6. Assistant responses and the usage-record `validation_outcome` have no storage location or write path.

None of these needs a change of paradigm. Most can be fixed by adding a `utils/contracts/` package, three more `store.py` primitives, a table of gate prerequisites, and an ownership table per file.

Severity: **H** = two compliant units will certainly not fit together. **M** = they will likely drift. **L** = cosmetic or local.

---

## H1. Finding and LocatorCandidate have no single shape across Runner and backend [H]

**Pair:** `runner/app/extract.py` + `locators.py` ↔ `backend/app/v1/inspection`, then onward to `v1/codegen`, `v1/maintenance` and `frontend/features/inspection`.

**How they diverge while both comply:**
- AD-14 makes Pydantic the single source of the contract for "backend ↔ Runner", but the Runner is a separate Python app in a separate image, and the spine doesn't say where the shared models live. The Runner team writes `attributes: {"aria-label": …, "data-testid": …}` as a raw DOM dict. The inspection team models FR-2 as flat fields (`aria_label`, `data_testid`) because the convention says "JSON keys are snake_case". `aria-*` keys can't be snake_case without being renamed, so each side renames them differently.
- AD-11 puts `fingerprint` on each Finding but doesn't say who computes it. The Runner computes `container` as `form#login`. The backend recomputes it from `attributes` as `form[name=login]`. Both comply, and the fingerprints never match across a rescan.
- `finding_id` (`f_001`, in DOM order): the Runner numbers all visited nodes, the backend renumbers after dropping hidden ones, and FR-3 marker numbers then point at different elements.
- A LocatorCandidate is a "Playwright Python expression" string. The Runner emits `page.get_by_role("button", name="Sign In")`. Codegen (AD-13) renders POM members as `self.page.get_by_role('button', name='Sign In')`. The AD-12 check that "every locator it uses must exist among the source Inspection's candidates" compares strings and fails on every locator (different receiver, different quotes). Alternatively, one team normalises and the other doesn't.
- The reliability rating (High/Medium/Low, FR-5) and ranking: the Runner ranks by type, the backend re-ranks by `match_count`, and the UI shows one order while codegen picks the other.

**Proposed rule: AD-21 Wire contracts live in one package shared by Runner and backend.**
`contracts/` (a top-level Python package installed into both images, Pydantic only, no logic beyond pure functions) defines `Finding`, `Fingerprint`, `LocatorCandidate`, `InspectionResult`, `RunResult` and `RunnerEvent`. The Runner is the **sole producer** of `finding_id`, `fingerprint`, LocatorCandidates, `match_count`, `rank` and `reliability`. The backend stores them verbatim and never recomputes them. Raw DOM attributes are kept in `attributes: dict[str, str]` with **original DOM names as keys**. This is the one documented exception to snake_case, and the derived fingerprint fields are snake_case. A LocatorCandidate is structured as `{strategy: role|label|test_id|css, args: {...}, expr: str, match_count, rank, reliability}`. Identity is `(strategy, canonical args)`, never `expr`. Codegen renders `expr` from `strategy`+`args` through one function, `contracts.locators.render(receiver)`, and the AD-12 check compares structured identity.

---

## H2. Version files have no envelope, and `content_sha256` is undefined [H]

**Pair:** `v1/test_design` (writes plan versions) ↔ `utils/gates.py` (checks hash) ↔ `v1/versions` (restore and diff).

**How they diverge:**
- AD-4 names `derived_from` and `restored_from` and AD-5 names `content_sha256`, but there is no envelope. test_design writes `{"version": 3, "plan": {...}, "derived_from": [...]}`, while versions-restore writes `{"n": 4, "content": {...}, "restored_from": 3}`. Both comply.
- `content_sha256` of *what*? Gates hashes the file bytes, which include `version`, `created_at` and `restored_from`. test_design hashes `json.dumps(plan)` without `sort_keys`. Approval of v3 records one hash, and the G1 check recomputes another. The gate never unlocks, or it unlocks on everything if someone "fixes" it by skipping the check.
- AD-4 says "diffs are text diffs between two version files". A diff of whole files always shows `version`, `created_at` and `restored_from` as changed, and AD-17 then reports a "byte-identical steps" violation for any repair.

**Proposed rule (tighten AD-4/AD-5):** Every file under `artifacts/` is
`{kind, id, version, session_id, created_at, created_by: <feature>, derived_from: [{kind,id,version}], restored_from: int|null, content_sha256, content: {...}}`.
`content_sha256 = sha256(canonical_json(content))`, where `canonical_json` means `sort_keys=True, separators=(",",":"), ensure_ascii=False`. It is implemented once as `utils/store.canonical_hash()` and stamped by `store.py` on write, never by features. Gates compare the stored field to a recomputed hash. Diffs (AD-4) and the AD-17 byte-identity check run on `canonical_json(content)` pretty-printed with `indent=2, sort_keys=True`, and on sub-paths of `content` for AD-17 (`content.steps`, `content.assertions`).

---

## H3. Version numbers are allocated non-atomically, which breaks immutability [H]

**Pair:** `v1/test_design` (tester edit) ↔ `v1/versions` (restore) running on the same `tp_…`. Also `v1/codegen` ↔ `v1/maintenance` on the same `code_…`.

**How they diverge:** Both list `artifacts/test_plan/tp_x/`, see `v3`, and write `v4.json` through `store.py`'s temp-fsync-rename. Rename replaces the file atomically, so the second write **silently overwrites** the first. AD-3 ("a version file is never changed") is broken without either unit doing anything wrong. FastAPI runs sync handlers in a threadpool, so a double-click is enough to trigger it.

**Proposed rule (tighten AD-3):** `store.py` exposes `append_version(kind, id, content, derived_from, restored_from=None) -> version`. It holds a per-artifact lock (`threading.Lock` keyed by path, because the backend is single-process: pin `uvicorn --workers 1` in AD-19) and publishes with `os.link(tmp, v{n}.json)`, or `rename` after an `O_EXCL` placeholder, so an existing version can never be replaced. Features never compute `n`. Any write to an existing `v{n}.json` path raises.

---

## H4. `session.json` has two writers in practice, and read-modify-write loses updates [H]

**Pairs:**
- (a) `v1/inspection` ↔ `v1/session`: AD-15 says "starting an Inspection … records G0 for its origin **on the Session**". AD-20 says origins live in `session.json`, "written only through `v1/session`". AD-1 forbids inspection importing session. Inspection can't record G0 without breaking one of the three.
- (b) Two `v1/session` handlers: a scope toggle (FR-11) and a goal edit (FR-10) from rapid UI actions. Both `read → mutate → store.write_json`. The rename is atomic, but the last writer wins and one edit is lost. This is the "clarification answer disappears" bug.
- (c) Origins are stored twice: in `session.json.origins` (AD-20) and as G0 records in `approvals.jsonl` (AD-5). Execution reads one, the Runner allow-list is built from the other, and they drift.

**Proposed rules:**
- **AD-20 tightened:** G0 is an approval record in `approvals.jsonl`, written by `utils/gates.record_g0(session_id, origin)`, which any feature may call. `session.json` keeps **no** origin list. "Approved origins" always means `gates.approved_origins(session_id)`. `runner_client` builds every job's allow-list from that call alone, so features can't pass their own lists.
- **AD-3 tightened:** `store.update_json(path, fn, expected_rev=None)` holds a per-file lock around read → `fn(doc)` → write and increments a `rev` field. Handlers that mutate `session.json` must use it. The API returns `rev`, and the frontend sends `If-Match: rev` on mutations. A mismatch returns 409 with the AD-14 envelope `code: "stale_session"`. Plain `write_json` on an existing mutable file is forbidden.
- **Ownership table (new, in the Structural Seed):** every path in the data layout lists exactly one owning feature (or `utils/*` helper) and its write mode: `create-once`, `append`, or `update_json`.

---

## H5. Gate prerequisites are not chained, so each feature checks a different set [H]

**Pair:** `v1/execution` ↔ `v1/codegen` ↔ `v1/maintenance` (with `frontend/features/execution`).

**How they diverge:**
- AD-5 has `gates.py` check "the target version is approved and its hash still matches" for one gate. Execution checks G3 on `code_x v2` and runs. Nobody checked that G2 (validation accepted) exists for v2, or that the AD-12 validation result exists at all. The frontend hides the Execute button until G2, but AD-5 says the UI must not be the only enforcement.
- G5 pins what? Maintenance approves the **repair** artifact `rep_y v1`, then writes `code_x v3`. Execution checks G3 on v3 and finds nothing, so either (i) maintenance also writes a G3 record ("becomes runnable", which bypasses AD-12 validation), or (ii) the tester must re-approve G2 and G3, which contradicts "becomes runnable". Two compliant teams pick different readings.
- G4 vs G3: a rerun of the *same* code version. Execution-team A requires G4. Execution-team B accepts the existing G3 because the hash still matches. "Rerun after revision" produces a *new* code version, which by AD-5 needs a fresh approval anyway, so G4's scope is undefined.
- G0's record shape `{artifact_kind, artifact_id, version, content_sha256}` doesn't fit an origin. Teams invent `version: 0` or `version: null` and `sha256("")`, and the gate checker crashes on one of them.
- `approvals.jsonl` is per session, but `artifacts/` is global. `gates.check(kind, id, version)` doesn't know which approvals file to read unless the artifact carries `session_id` (see H2).

**Proposed rule (tighten AD-5): a table of gate preconditions, enforced only in `gates.require(action, …)`.**

| Action (called by) | `gates.require` checks |
|---|---|
| `codegen.generate(tp v)` | G1(tp, v) |
| `execution.run(code v)` | validation(code v) passed **and** G2(code v) **and** G3(code v) **and** G0 for every origin the plan touches |
| `execution.rerun(run r)` | G4(run r, code v), where v is the same version as r; a new code version goes through `run` |
| `maintenance.apply(rep v)` | G5(rep v), then `store.append_version(test_code, …, derived_from=[rep v])`; the new code version is **unapproved** and must pass validation, G2 and G3 like any other |

G0 records use `{gate:"G0", artifact_kind:"origin", artifact_id:<origin>, version:1, content_sha256:sha256(origin)}`. Features call `gates.require(action, …)` and never check individual gates themselves. Run it in an import-linter or grep check in CI-equivalent pre-commit: no `v1/*` reads `approvals.jsonl`.

---

## H6. Model call records: `validation_outcome` and `response_id` have no owner [H]

**Pair:** `utils/model_client.py` ↔ `utils/agent_loop.py` ↔ `v1/assistant` (and `v1/usage`).

**How they diverge:**
- AD-8 says only `model_client` writes the record, and the record includes `validation_outcome`. But validation happens in `agent_loop` *after* the call returns. Compliant model_client writes `validation_outcome: null`. Then either agent_loop appends a second "outcome" record (which violates "one record per call"), or it rewrites the line (which violates append-only). `v1/usage` builds the FR-19 badge by grouping on `response_id`, and either double-counts or shows "unknown".
- `response_id` (`resp_`): agent_loop allocates one per loop, and the assistant feature allocates another for the stored response. The badge can't join them.
- `reused: true`: no cache is specified. The assistant feature caches summaries by `(scope, goal)` and writes nothing, because model_client was never called. Or it fakes a model_client call to log `reused`. AD-18 averages then differ between the two.
- Concurrent appends to `model_calls.jsonl`: AD-3's atomic rename doesn't apply to appends. Two simultaneous calls (assistant + clarification) interleave partial lines once a line exceeds PIPE_BUF.
- **Assistant responses aren't stored anywhere in the data layout.** FR-17 requires validation outcomes "recorded with the response", and FR-13 needs the clarification conversation. `v1/assistant` can't write `session.json` (AD-20). So it invents `data/assistant/…`, `artifacts/summary/…` (not a listed kind), or nothing.

**Proposed rules:**
- **AD-8 tightened:** `agent_loop.run(...)` allocates `response_id` and passes it plus `attempt` to `model_client.call(...)`. `model_client.call()` *returns* the measurements without writing. `agent_loop` calls `model_client.record(call, validation_outcome)` once per attempt, after validating that attempt. `model_client` stays the only writer. Appends go through `store.append_jsonl()`, which uses a process lock plus `O_APPEND` with one `write()` per line. Cache hits are recorded by `agent_loop` through `model_client.record_reused(response_id, source_call_id)`. The cache lives only in `agent_loop`, keyed by `canonical_hash(prompt_payload)`.
- **Data layout addition:** `sessions/{ses_id}/responses/{resp_id}.json` (create-once, owner `v1/assistant`, and `v1/session` for clarification turns), holding `{response_id, kind: summary|clarification|repair_explanation, sections, blocked_claims, validation: {attempts, outcome}, call_ids}`. `session.json` stores only the ordered list of clarification `response_id`s and tester answers.

---

## H7. Runner exchange-volume layout and job identity are undefined [H]

**Pair:** `utils/runner_client.py` + `v1/execution` ↔ `runner/app/run_tests.py` (and `v1/inspection` ↔ `runner/app/extract.py`).

**How they diverge:**
- AD-10 gives `tests/` (read-only) and `out/` (writable) and nothing else. The backend writes `tests/test_login.py` + `tests/pages/login_page.py` for job 1, the tester queues job 2 (FIFO), and the backend overwrites `tests/` while job 1's pytest is still collecting. Runner FIFO doesn't protect a shared directory the backend writes *outside* the queue.
- Job identity: the Runner allocates `job_id` and the backend allocates `run_` and `ins_`. The SSE envelope carries `job_id`. The frontend subscribes by `run_id`, so events never match, or the backend keeps a map nobody owns.
- Results: the Runner writes `out/results.json` (pytest-json) while the backend expects `out/{job}/run.json` in the `RunResult` shape. The screenshot path for an inspection is `out/screenshot.png` vs `out/{job}/screenshot.png`. Import timing: does the backend import on the SSE `completed` event or on the `POST` response?
- Origin allow-list during **test runs**: AD-15 has the Runner apply `page.route`, but pytest-playwright creates its own `page` fixture in a pytest subprocess. If codegen emits a `conftest.py` with the route and the Runner also injects one, they collide. If neither does, tests reach any origin.
- POM import path: codegen emits `from pages.login_page import LoginPage`, while the Runner runs `pytest /exchange/tests/test_login.py` with a rootdir where `pages` isn't importable.

**Proposed rule: AD-22 Exchange-volume protocol.**
- The backend allocates every ID (`ins_`, `run_`) and passes it as `job_id`. The Runner never mints IDs. The SSE `job_id` is always that backend ID.
- Layout: `tests/{job_id}/` (written by the backend before `POST /run_tests`, never modified after) contains `pages/*.py`, `test_*.py` and `manifest.json` `{job_id, code_id, version, content_sha256, allowed_origins}`. Output goes to `out/{job_id}/`, containing `result.json` (the `contracts.RunResult` / `InspectionResult` shape), `screenshots/`, `crops/` and `trace.zip`. The Runner writes `out/{job_id}/DONE` last.
- The backend imports into `data/` only after reading `DONE` (triggered by the Runner's terminal SSE event) and deletes both job directories once the import succeeds.
- The Runner owns `conftest.py` (fresh context per test, `page.route` allow-list from `manifest.json`, `browser_ms`/`test_ms` timing), and copies it into the rootdir. Codegen must not emit `conftest.py`, `pytest.ini` or fixtures. POM imports are `from pages.<module> import <Class>` with rootdir `tests/{job_id}`.
- The Runner refuses a job whose manifest hash doesn't match the files, which also closes the "run something different from what was approved" path in AD-5.

---

## H8. Findings are referenced without the Inspection, across multiple Inspections [M→H in Phase 2]

**Pair:** `v1/session` (Scope) ↔ `utils/agent_loop` (validates "cited ids … in Scope") ↔ `v1/maintenance` and `v1/codegen`.

**How they diverge:** `finding_id` is unique only *within* an Inspection (AD-11). A Session has many Inspections: FR-9 multi-page, FR-7 re-inspect after login, every rescan (AD-4 "a rescan creates a new Inspection"). Session stores Scope as `["f_003","f_007"]` for the latest Inspection. The assistant validates a citation `f_003` against whichever Inspection it loads. After a re-inspect after login renumbers the DOM, `f_003` silently means a different element, and validation **passes** with a wrong grounding. That is a direct NFR-1 breach. The frontend links FR-16 evidence to `f_003` in the currently displayed Inspection.

**Proposed rule (tighten AD-11/AD-20):** Outside an Inspection file, a Finding is always referenced as `FindingRef = {inspection_id, finding_id}`. On the wire it may be the string `"ins_…/f_003"`. Scope is `{inspection_id, finding_ids[], filters}` and is bound to exactly **one** Inspection. Changing the active Inspection clears Scope or carries it over explicitly by running the AD-11 matcher. The model sees and cites only `f_…` ids within a prompt that covers one Inspection. `agent_loop` qualifies them with the prompt's `inspection_id` before storing.

---

## H9. Confidence and clarification have one owner on paper and two in practice [M]

**Pair:** `v1/session` (AD-16 confidence function, FR-13 clarification) ↔ `v1/assistant` (FR-14: "if the goal is not actionable, clarify before summarizing") ↔ `v1/maintenance` (AD-5/AD-11 ambiguous-match Clarification requests).

**How they diverge:** The assistant must know whether the goal is actionable, but it can't import `v1/session` (AD-1). It either recomputes confidence with its own copy, which AD-16 exists to prevent, or it reads a stale value. Maintenance produces "Clarification requests" too, with a different shape, a different blocking mechanism ("block the step until … answers or explicitly skips") and different storage. So the frontend's clarification panel needs two components, and "skip" means two different things.

**Proposed rule:**
- `session.json` stores `confidence: {score, signals, threshold, goal_rev, scope_rev}`, recomputed and written by `v1/session` on every goal, scope or answer change. Other features read the stored value and treat it as stale if `goal_rev` or `scope_rev` differ, which returns 409 `confidence_stale`. Alternatively, move the pure function to `utils/confidence.py`. Either works, but the spine should choose one.
- **One Clarification entity:** `{clr_id, session_id, origin: goal|rescan_match, subject_ref, question, options, status: open|answered|skipped, answer}`. It is stored in `sessions/{ses_id}/clarifications/{clr_id}.json`, created by `utils/clarify.open()` (any feature) and resolved only through `v1/session` routes. A gated step that is blocked checks `clarify.open_for(subject_ref)` inside `gates.require`. Add the `clr_` ID prefix.

---

## H10. Test plan, test case and test code granularity is undefined [M]

**Pair:** `v1/test_design` ↔ `v1/codegen` ↔ `v1/versions` and `frontend/features/test_design`.

**How they diverge:**
- `tc_` is an ID prefix, and AD-4 says "each … test case edit creates v{n+1}", but the data layout's artifact kinds are `test_plan | test_code | repair`, with **no `test_case`**. Team A embeds cases inside the plan version (so editing a case bumps the plan). Team B stores `artifacts/test_case/tc_…/v{n}`, using a kind the layout doesn't list.
- G1 is per plan version. AD-13 generates "one `test_<case>.py` per **approved test case**". Can a single case be approved, or only the whole plan?
- Is `test_code` one artifact per plan (POM + all tests) or one per case? AD-13 says "one page object class per inspected page". If two plans touch the same page, two POMs exist in different `code_` artifacts, and the AD-12 locator check runs against whichever Inspection each `derived_from` names.
- AD-17's "steps and assertions of the approved test case stay byte-identical": the steps live in the plan (model JSON) *and* in generated code. Which one is diffed?

**Proposed rule (tighten AD-4/AD-13):** Test cases are embedded in the test plan: `content.cases[] = {case_id: "tc_…", title, finding_refs[], steps[], assertions[]}`. `tc_` ids are stable across plan versions and copied forward, so test cases aren't separately versioned artifacts. Remove the "test case edit" phrase from AD-4. G1 approves the whole plan version. `test_code` is one artifact per plan, `code_…`, whose `content` is `{plan_ref, inspection_refs[], files: {path: source}, step_json: {case_id: [...]}, validation: {...}}`. The AD-17 check diffs `content.step_json`'s steps and assertions against the source plan version's `cases[]` after removing locator fields.

---

## H11. SSE events are untyped and have two ID namespaces [M]

**Pair:** `utils/events.py` + `utils/runner_client.py` ↔ `frontend/src/api` hooks (and `runner/app` `GET /events`).

**How they diverge:** AD-14 fixes the envelope `{event, job_id, step, status, ts, data}` but not the vocabulary. The Runner emits `status: "running"`, while agent_loop emits `"in_progress"`. One team uses `event: "progress"` with steps in `step`, and another uses `event: "inspection.extract"`. `openapi-typescript` generates types only from OpenAPI, and SSE payloads aren't in OpenAPI, so the frontend hand-writes them, which AD-14 forbids. Does the backend relay Runner events verbatim, or translate them? Is the stream per job or per session (`GET /api/v1/sessions/{id}/events` vs `/jobs/{id}/events`)?

**Proposed rule (tighten AD-14):** `contracts.events` defines `event: Literal[...]` per producer (`inspection.*`, `run.*`, `assistant.*`, `codegen.*`), `status: Literal["queued","running","succeeded","failed","blocked"]`, and one `data` model per event, combined into a discriminated union `SseEvent`. That union is exposed in OpenAPI through a documented schema-only route (or `openapi_extra`), so the TypeScript is generated. There is one stream per Session, `GET /api/v1/sessions/{ses_id}/events`, and `job_id` is always a backend ID (H7). `utils/events.py` is the only emitter, and `runner_client` translates Runner events into this union. The frontend never connects to the Runner except the noVNC iframe.

---

## H12. Inspection is "never changed" but has a lifecycle [M]

**Pair:** `v1/inspection` ↔ `v1/maintenance`, `v1/versions` and `frontend/features/inspection`.

**How they diverge:** `inspection.json` carries `status` (layout comment) and FR-6 needs partial, retry and progress states. Team A creates `inspection.json` at job start (`status: running`) and rewrites it at the end, which breaks "stored Inspections are never changed". Team B writes it only at the end, so a crash mid-run leaves no record, and FR-6's "never an empty screen without a reason" fails after a restart. A retry (FR-6) and a re-inspect after login (FR-7): new `ins_` or the same one?

**Proposed rule:** `inspection.json` is **create-once at a terminal state** (`complete | partial | failed`, with the AD-14 failure-kind enum). Progress before that exists only as SSE events plus a `sessions/{ses_id}/jobs/{job_id}.json` status file owned by `utils/runner_client` through `update_json`. Every retry, re-inspect and rescan is a new `ins_`, with `derived_from: {inspection_id, reason: retry|reinspect|rescan}`. Even an unreachable result writes a `failed` Inspection with zero Findings.

---

## H13. The naming convention contradicts the data layout [L]

**Pair:** `v1/codegen` ↔ `frontend/features/codegen` ↔ `data/artifacts/test_code`.

**How they diverge:** The convention says "one feature folder name is reused across backend route prefix, frontend folder and data kind". But the data kinds are `test_plan`, `test_code` and `repair`, while the features are `test_design`, `codegen` and `maintenance`. One team names routes `/api/v1/codegen/…`, another `/api/v1/test_code/…`. The ID prefix `code_` matches neither.

**Proposed rule:** Route prefix = feature folder = frontend folder. Data kind = the entity name, from a fixed table (`test_plan`→`tp_`→owner `test_design`; `test_code`→`code_`→owner `codegen`, with `maintenance` appending through G5 per H5; `repair`→`rep_`→owner `maintenance`). The convention row then says "feature name ≠ entity kind; see the ownership table".

---

## H14. The rescan scorer has no defined home [L]

**Pair:** `v1/maintenance` ↔ `v1/session` (carrying Scope across a re-inspect, H8) ↔ `v1/inspection`.

AD-11 requires "one shared scoring function" but doesn't name its home. If it starts in `v1/maintenance` (Phase 2), Phase 1's Scope carry-over writes its own. **Rule:** `utils/matching.py` (pure, deterministic, reads `contracts.Fingerprint`), with margin and threshold from config. It is the only matcher.

---

## H15. Locator live-check context [L]

**Pair:** `v1/codegen` validation (AD-12 "match exactly one element on the live page") ↔ `runner/app`.

Which browser context runs the live check: the long-lived inspection context (logged in, FR-7) or a fresh one (AD-20)? Against a login-gated page, the two give different `match_count`s, so validation passes and the run fails, or the reverse. **Rule:** the live locator check is a Runner job type `POST /verify_locators` that runs in the **inspection context** of the Session and records `context: inspection` in the validation result. Its outcome is advisory for login-gated pages until the credential item in Deferred is decided.

---

## Summary of proposed spine changes

| # | Change | Type |
|---|---|---|
| H1 | AD-21: shared `contracts/` package; Runner is the sole producer of Finding, fingerprint and locators; structured LocatorCandidate | new AD |
| H2 | Version envelope plus `canonical_hash` in `store.py` | tighten AD-4/AD-5 |
| H3 | `store.append_version` with exclusive create; single worker | tighten AD-3, AD-19 |
| H4 | G0 only in approvals; `store.update_json` with `rev`/If-Match; ownership table | tighten AD-3/AD-15/AD-20 |
| H5 | Gate precondition table; `gates.require(action)` only | tighten AD-5 |
| H6 | `agent_loop` owns `response_id` and outcome; `model_client.record()`; `responses/` storage; locked JSONL append | tighten AD-8, layout |
| H7 | AD-22: exchange-volume protocol, backend-minted job IDs, Runner-owned conftest | new AD |
| H8 | `FindingRef {inspection_id, finding_id}`; Scope bound to one Inspection | tighten AD-11/AD-20 |
| H9 | Stored confidence with revs; one Clarification entity (`clr_`) | tighten AD-16, layout |
| H10 | Cases embedded in plan; one `test_code` per plan; AD-17 diff target | tighten AD-4/AD-13/AD-17 |
| H11 | Typed SSE union in OpenAPI; one stream per Session; backend-only emitter | tighten AD-14 |
| H12 | Inspection create-once at a terminal state; jobs status file | tighten AD-4 |
| H13 | Separate the feature name from the entity kind | convention |
| H14 | `utils/matching.py` | tighten AD-11 |
| H15 | `/verify_locators` in the inspection context | tighten AD-12 |
