# Reconcile Review: ARCHITECTURE-SPINE.md vs inputs

- Spine: `ARCHITECTURE-SPINE.md` (draft, 2026-11-20)
- Inputs: `GenAI_Fall26_project.md` (brief), `prds/prd-Test-Tpt-2026-11-20/prd.md` (Phase 1 PRD), `.memlog.md` (user decisions; later entries supersede earlier)
- Date: 2026-11-20
- Spine was not edited.

## Verdict

**Mostly reconciled, with gaps to fix.** Every memlog decision that is still in force is reflected faithfully. That includes the single 4B model for both roles (which supersedes the 8B codegen decision), Docker Runner with noVNC, JSON storage, append-only versions, hash-pinned approvals, deterministic matching, templated codegen, validation before execution, and the stack versions. Most brief items in the checklist are covered. The open problems are one real contradiction in Phase 2 test design: assertion targets are limited to inspected interactive Findings. There are also several quiet requirements that the spine weakens or leaves without an owner: container egress and hardening, rate limits and resource limits, page-level averages, test-design clarification, an unreachable local target site, and code-literal escaping.

## Coverage checklist (brief items requested)

| Brief item | Source | Spine coverage | Status |
|---|---|---|---|
| Approval points (plan, code review, execute, rerun, repair) | brief L18, L80-93, PRD FR-23 | AD-5 gates G0–G5 plus clarification blocking | Covered |
| Validation (syntax plus locators vs observed elements, uniqueness) | brief L84, L116, FR-24 | AD-12, AD-6 | Covered, but see G1 (dynamic assertion targets) |
| Sandboxing / no unrestricted host commands / controlled FS | brief L126 | AD-10 mounts, AD-2 | Partly. The container network egress rule from the memlog was dropped, and container hardening is not stated (G2) |
| Limit execution to approved target | brief L126 | AD-15 G0 plus `page.route` | Partly. `page.route` covers only browser traffic, not test-process sockets (G2). A target on host localhost can't be reached (G5) |
| Webpage content as data | brief L126 | AD-9 data blocks, no tools | Covered for prompts. Not covered for codegen string literals (G6) |
| Model vs browser timing separate | brief L128 | AD-18, AD-8 `load_ms` | Covered |
| Token counts labeled as estimates | brief L128 | AD-8 `tokens_source` | Covered in the data. The UI labeling rule is implicit (minor) |
| Rate limits documented | brief L128 | none (AD-7 only enables cloud) | **Missing** (G3) |
| Reused vs fresh distinguished | brief L128 | AD-8 `reused`, AD-18 | Partly. No cache or reuse policy is defined, so `reused` has no producer (minor) |
| Keep real failures visible / don't weaken assertions | brief L120 | AD-17 | Covered |
| Versioning: store, text diff, restore | brief L93, L105 | AD-4 | Covered. Small inconsistency: no `test_case` kind in the data layout. The diff target should be the code text, not the JSON wrapper (minor) |
| Per-call usage plus session/page average | brief L94-95 | AD-8, AD-18 | Partly. The record has no page/inspection key, so page-level averages can't be computed (G4) |
| Ambiguous change clarification | brief L91-92, L105, L122 | AD-11, AD-5 | Covered for rescan. **Missing** for test design and expected behavior (G1b) |
| Setup reproducibility | brief L96, L66, NFR-5 | AD-19, Stack | Partly. `uv` is "latest at setup", the model digest isn't pinned, the npm lockfile isn't mentioned, and the docker-group step on Linux is missing (minor) |
| Resource limits documented | brief L22, L96, FR-26 | Map row "docs/, this spine" | **Weak.** The spine records no practical limits (VRAM/RAM budget, container limits, response-time target) and names no owner doc for them (G3) |

## Gaps (ordered by impact)

### G1. Assertion targets for expected results contradict "locators only from Inspection candidates" (and test-design clarification has no owner)
- **Source:** brief L81 ("actions and meaningful expected results"), L118 ("Distinguish page observations from assumptions about business rules. Ask the tester to confirm expected behavior"), L120 (meaningful assertions). PRD FR-2 extracts *interactive* elements only.
- **Problem:** AD-12 requires every locator to "exist among the source Inspection's candidates **and** match exactly one element on the live page". AD-13 lets the model refer only to page object members built from verified locators. Meaningful expected results usually target elements that don't exist yet or aren't interactive: an error message after submit, a post-login heading, a URL change. With these rules those assertions either can't be expressed or fail pre-execution validation. Tests would drift toward weak assertions such as "button is visible", which the brief warns against.
- **G1b:** P2-TestDesign maps to AD-4/5/6 only. There's no rule that each expected result is tagged with its source (`observed` / `tester_requirement` / `assumption`), or that an unconfirmed business-rule assumption blocks G1 until the tester confirms it. The clarification blocking in AD-5 names only FR-13 and rescan ambiguity.
- **Fix:** Add an AD (or extend AD-12/AD-13) defining an assertion-target class `expected`. It covers tester-confirmed text, role, or URL that wasn't observed in the inspected state. It's stored in the approved plan, rendered via `get_by_role`/`get_by_text`/`expect(page).to_have_url`, exempt from the live single-match check before G3, and checked at run time. Alternatively, allow tester-driven "inspect after action" states as additional Inspections. Require every expected result to carry `basis: observed|tester_confirmed|assumption`, and let G1 open only when no `assumption` remains unconfirmed. Add test design to the list of clarification blockers in AD-5.

### G2. Runner isolation is weaker than the memlog decision
- **Source:** memlog L30 ("egress limited to approved target origin (Playwright route blocking **+ container network rules**); no host shell"). Brief L126 ("restricted runner process or container ... prevent unrestricted host commands").
- **Problem:** AD-15 enforces origin limits only via `page.route`, which only covers browser requests. Generated pytest code is Python running in the same container and could open sockets or call `subprocess`. The spine also doesn't state the container hardening the brief implies: non-root user, no Docker socket mount, no `privileged`, read-only root filesystem, dropped capabilities, CPU/memory limits, and separation of the Runner API process from the test process (a per-run subprocess with a timeout).
- **Fix:** Extend AD-10 with a hardening list: non-root, `cap_drop: ALL`, `no-new-privileges`, read-only rootfs except `out/` and tmp, no docker.sock, `mem_limit`/`cpus`, and a per-run timeout. Add a network rule, such as an internal compose network plus an egress proxy or allowlist limited to the G0 origins, so origin limits apply beyond `page.route`. Since AD-13 means no model-authored free code reaches the files, state that and add a generator check that the produced test imports only the allowed modules.

### G3. Rate limits and practical resource limits are not documented anywhere
- **Source:** brief L22 ("Document ... practical resource limits"), L128 ("Document rate limits and resource constraints"), L96. PRD FR-26, NFR-2, NFR-3. Memlog L11 (Groq free tier, sample 30 RPM / 8k TPM / 200k TPD). Addendum L7.
- **Problem:** The spine allows a cloud provider (AD-7) but has no rule for its rate limits: no documentation, client-side throttle, 429 handling, or recording of rate-limit waits separate from `response_ms`. FR-26 is mapped to "docs/ governed by this spine", but the spine states no limits: VRAM budget (~2.5 GB model plus KV cache at 8k), the 14 GB RAM budget across the Docker VM, Chromium, Xvfb and Ollama, container limits, the response-time target from NFR-3, and the benchmark that fills them in. Teammates on macOS and Windows have different hardware, and nothing says the limits are recorded per machine.
- **Fix:** Add an AD or convention: `docs/resources.md` (owned by the design doc) records the model, quantization, `num_ctx`, measured VRAM/RAM, container `mem_limit`, measured p50/p95 response time per role, and the NFR-3 target, filled in from the Phase 1 benchmark. For cloud, `model_client` applies the configured RPM/TPM limits, handles 429 with backoff, records `wait_ms` separately, and the documented free-tier limits are copied into config and the docs.

### G4. Page-level average response time is impossible with the current record shape
- **Source:** brief L94-95 ("per-call token usage and response time, plus a session or page-level average response time"). PRD FR-21.
- **Problem:** The AD-8 record has `session_id` and `response_id`, but no `inspection_id`, page URL, or `feature` key. AD-18 promises "averages for a Session and for a page" but has no key to group by page. The per-call usage display is also defined only for Phase 1 assistant responses (FR-19 badge). Phase 2 calls (test design, codegen steps, repair explanation) have no stated display surface.
- **Fix:** Add `inspection_id` (or `page_url`) and `feature` to the AD-8 record. State that the usage badge (FR-19) is a shared UI component attached to every model-backed output, including test plans, code versions and repair proposals, with session and page averages shown in `v1/usage`.

### G5. A target site on the tester's host is unreachable from the Runner container
- **Source:** brief L26 ("small instructor-supplied website and a modified version"), L103 (rescan "the modified website"). Memlog L39 (compose; Ollama via `host.docker.internal`).
- **Problem:** The instructor site will probably be run locally (`http://localhost:PORT`). Inside the Runner container, `localhost` is the container itself. AD-19 maps `host.docker.internal` only for the backend to reach Ollama. AD-15 approves origins by the URL the tester typed. Nothing covers rewriting or mapping a host-local target, how G0 origins compare when the hostname is rewritten, or switching between the original and modified site (two origins or ports means two G0 approvals, which affects maintenance comparisons).
- **Fix:** Add `extra_hosts: host.docker.internal:host-gateway` to the `runner` service. Add a rule: a tester URL on `localhost`/`127.0.0.1` is mapped to `host.docker.internal` for the Runner while the tester-facing URL stays as typed, and G0 stores both. Also say that a rescan of the modified site, if it's on a new origin, needs a new G0 and still compares by Finding fingerprint, not URL.

### G6. Page-derived strings flow into generated Python code without an escaping rule
- **Source:** brief L126 ("Treat webpage content as data, not as instructions"). AD-12/AD-13 build code from accessible names and attributes.
- **Problem:** AD-9 covers prompts only. The generator embeds observed names (for example `get_by_role("button", name=...)`) and model-supplied step values into `.py` templates. A crafted label containing quotes or newlines could inject code into the generated test, which then runs in the Runner.
- **Fix:** Add to AD-13: every page-derived or model-supplied value enters code only through a literal-escaping helper (`repr()` / `json.dumps`), never by string formatting into code. The validation step re-parses with `ast` and confirms the generated AST contains only the allowed call shapes.

## Minor items

- **M1 AD tags:** AD-17, AD-18 and AD-20 lack `[ADOPTED]`, but all three derive from adopted memlog decisions (AD-20 from memlog L37). Tag them for consistency.
- **M2 Test case versioning:** AD-4 says "test case" versions exist, and IDs include `tc_`, but the data layout's `kind` list has only `test_plan | test_code | repair`. Add `test_case` or state that cases are versioned inside the plan. Also say that code diffs are computed on the rendered Python source, not the JSON wrapper.
- **M3 Reuse has no producer:** AD-8 records `reused: true` "from cache", but no cache policy exists. Define what may be reused (for example, an identical prompt hash within a Session, or a stored Inspection reopened instead of rescanned) and show a "reused" label in the UI. Also note that Ollama's `prompt_eval_count` can be lower when a cached prompt prefix is reused. Record that, or label it.
- **M4 Rescan is user-triggered:** The brief (L89) says "on a user-requested rescan". The spine shows RESCAN without saying it starts only on tester request. State that it never starts automatically.
- **M5 Cloud fallback data egress:** Memlog L14 and PRD §4.5 ask whether page content may leave the machine. AD-7 makes cloud opt-in but doesn't say that enabling it sends Findings off the machine. Add a UI or docs warning.
- **M6 Run evidence shape:** The brief (L86) requires "pass/fail results, screenshots, and failure details". `run.json` has no stated fields for the failing step, assertion message, expected vs actual, or the screenshot per failure. Name a minimal run result schema, with `browser_ms` and `test_ms` from AD-18.
- **M7 Setup reproducibility:** "uv latest at setup" isn't pinned. Pin the uv version, commit `package-lock.json`, record the Ollama model digest (`ollama show`), and list the Linux docker-group step from memlog L33 in the setup docs. The memlog L19-B deliverable "interactive HTML walkthrough" isn't in the `docs/` seed, so add it.
- **M8 Credentials:** Deferred, which matches the memlog. FR-7 says credentials are never stored, so add a one-line rule that the long-lived inspection context (AD-20) is never persisted to disk (no `storage_state` saved) until the deferred decision is made.

## Memlog decisions verified as reflected

React+TS+Vite+TanStack with plain CSS. Single `qwen3:4b-instruct-2507` q4_K_M for both roles with think off, which supersedes 8B codegen, plus the challengers and the 8B upgrade path. Cloud off by default, labeled, with the key from env. ModelClient as the only gateway and only writer of records. Validated schema-constrained JSON with no tools or vision. Docker Runner on the Playwright image with a matching tag, noVNC by default and X11 optional on Linux. A narrow Runner HTTP API with one job at a time. Separate browser contexts. Compose with Ollama on the host. Credentials deferred. JSON storage with atomic writes. Append-only versions, restore as a new version, hash-pinned approvals, and derivation links. Deterministic fingerprints and scoring, with clarification on near-ties. `utils/` + `v1/` with no layers. Python 3.12, FastAPI, Pydantic, uv. Types generated from OpenAPI. REST + SSE with no token streaming. Prompt data blocks. Per-feature prompts on shared helpers. Code-computed confidence. 2 retries. One POM per page and one test per case. ast + ruff + locator check before execution. G0 origin approval. Monorepo layout. Stack versions match the registry check. Embeddings deferred.
