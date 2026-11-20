---
title: Human-in-the-Loop Web Testing Assistant — Phase 1 PRD
status: draft
created: 2026-11-20
updated: 2026-11-20
---

# PRD: Human-in-the-Loop Web Testing Assistant (Phase 1)
*Working title — confirm.*

## 1. Vision

A web workbench where a human tester points an assistant at a page and gets back an accurate, evidence-linked picture of what is actually there: every interactive element, its real attributes, and candidate locators. The tester steers it with a testing goal and by selecting elements. A locally run model summarizes only what was observed. It never guesses; where evidence is thin, it says so or asks.

Phase 1 proves this foundation and the architecture later phases build on: test design, Playwright generation, supervised execution, and maintenance after page changes.

## 2. Target User

### 2.1 Jobs To Be Done
- When I land on an unfamiliar page, I want to see its interactive elements and their real behavior-relevant attributes quickly, so I don't waste time exploring manually.
- When deciding what to test, I want suggestions grounded in what the page actually contains, so I can find edge cases without guessing.
- When the assistant tells me something, I want to trace it to observed evidence, so I can trust it.

### 2.2 Primary audience
QA tester (course framing: the TA and instructor evaluating the system in a demo on an instructor-supplied site).

## 3. Glossary
*Used verbatim throughout this PRD; no synonyms.*

- **Inspection** — A recorded scan of one page: its Findings plus the source URL and capture time. Belongs to a Session. Stored in the Inspection store.
- **Finding** — One extracted interactive element, with its observed label, attributes, and Locator candidates, linked to the source page of its Inspection.
- **Locator candidate** — A proposed way to find a Finding on the page (role, test id, CSS, XPath, etc.), derived from observed attributes.
- **Testing goal** — The tester's stated intent for the page, in their own words.
- **Scope** — The set of Findings the tester has selected or narrowed to; the only Findings the assistant uses for a given request.
- **Approval gate** — A point where the system stops until the tester explicitly approves before proceeding.
- **Runner** — The isolated browser process that opens and inspects pages (and, in later phases, executes tests).
- **Evidence** — Data the system actually observed, such as DOM attributes, a screenshot, or a URL. The only material the assistant may cite.
- **Grounded statement** — An assistant claim linked to one or more pieces of Evidence. Claims without Evidence are labeled Unverified or not made.
- **Unverified** — The label for anything the assistant could not observe, e.g. "cannot confirm authentication works without submitting the form."
- **Clarification request** — The assistant asking the tester a question because available Evidence is insufficient.
- **Model call record** — One entry per model call: model and version, prompt size, tokens used, response time, and hardware/API setup. Serves as feasibility evidence; later phases reuse it for per-call usage display.
- **Inspection store** — Persistent storage of Inspections, so later steps refer to what was actually observed and later phases can compare against it.
- **Session** — One tester working on one page or site from start to finish.
- **Agent loop** — The assistant's hand-written cycle for interacting with the model (build grounded prompt, call model, validate output, respond or ask). Written without agent frameworks such as CrewAI or LangChain; ordinary frameworks elsewhere (web, UI, Playwright) are allowed.

## 4. Features

### 4.1 Page Inspection
*Rubric: Working page inspection (3 pts).*

**Description:** The tester enters a URL and starts an Inspection. The Runner opens a visible browser on that page and extracts every interactive element as a Finding: its observed label or text, real DOM attributes, visibility, and ranked Locator candidates. The tester sees two linked views: a full-page screenshot with numbered markers, and a Findings table whose rows carry the same numbers. Clicking a Finding opens a detail panel with everything observed about that element. Every Finding is traceable to an actual element on the page, and the system never reports an element it did not observe. When inspection fails fully or partly, the tester sees which failure occurred and what was still captured, never an empty or silent screen. Single-page inspection is the default; tester-driven exploration of further pages is optional.

**Functional Requirements:**

#### FR-1: Start an Inspection from a URL
The tester can enter a URL and start an Inspection. The Runner opens a visible browser window on that page.

**Consequences (testable):**
- A browser window visibly opens on the tester's machine and loads the URL.
- A malformed URL is rejected with a message before any browser launches.
- The Inspection records the requested URL, the final URL after redirects, and the capture time.

#### FR-2: Extract interactive elements as Findings
The system extracts each interactive element on the loaded page as a Finding.

**Consequences (testable):**
- Covered elements include inputs, textareas, selects, buttons, links, checkboxes, radio buttons, and elements with interactive ARIA roles.
- Each Finding records: tag, type, accessible name / label, visible text, attributes as present in the DOM (id, name, type, placeholder, required, disabled, pattern, min/max length, aria-*, data-testid), visibility state, on-page position, and its containing landmark or form (e.g. `form#login`), so Scope can be filtered by container (FR-12).
- Attribute values match the DOM exactly. Extraction is deterministic code reading the DOM; the model plays no part in producing Findings (it only interprets them).
- Each Finding has an ID that is stable and unique within its Inspection.

#### FR-3: Show linked screenshot and Findings table
After an Inspection completes, the tester sees a full-page screenshot with a numbered marker on each Finding, and a Findings table (number, element name, type, status).

**Consequences (testable):**
- Marker numbers on the screenshot match row numbers in the table one-to-one.
- Status distinguishes at least Detected, Hidden, and Inaccessible.
- Selecting a table row highlights its marker. *(Stretch: clicking a marker on the screenshot selects its row.)*

#### FR-4: Finding detail panel
The tester can open any Finding to see its detail panel.

**Consequences (testable):**
- The panel shows the element name and type, a screenshot crop with the element highlighted, its relevant DOM/HTML snippet, all observed attributes, visibility, and its Locator candidates (FR-5).
- Validation rules appear only when observed as attributes (e.g. required, type=email, pattern, maxlength). Behavior not observed is not claimed.
- Testing suggestions shown in the panel come from the grounded assistant (§4.3) and are visibly marked as assistant output, separate from observed Evidence.

#### FR-5: Ranked, verified Locator candidates
The system produces several Locator candidates per Finding, ranked by reliability, and verifies each one against the live page.

**Consequences (testable):**
- Ranking prefers role / accessible-name and label locators, then test IDs, then CSS. XPath and positional selectors are never recommended automatically.
- Candidates are displayed and copied in Playwright Python syntax, matching the generated tests, e.g. `page.get_by_role("button", name="Sign In")`, `page.get_by_label("Password")`, `page.get_by_test_id("login-button")`, `page.locator('button[type="submit"]')`.
- Each candidate shows its match count on the inspected page. A candidate matching anything other than exactly one element is ranked down and flagged, whatever its type.
- Each candidate shows a reliability rating (High / Medium / Low).
- The best candidate is shown prominently; alternatives expand on demand; the tester can copy any candidate.

#### FR-6: Distinct failure states with no invented Findings
When an Inspection cannot complete, the system reports which failure occurred and keeps whatever it did capture.

**Consequences (testable):**
- Distinct messages exist for: URL unreachable (with possible causes), load timeout (after a configurable limit, with progress shown while loading), login required, and partial inspection.
- A partial result shows counts of inspected versus inaccessible elements, the reason, and the Findings that were captured.
- The system never shows an empty results screen without a reason, and never creates a Finding for an element it could not inspect.
- The tester can retry any failed or partial Inspection.

#### FR-7: Authenticate manually, then re-inspect
When a page requires login, the tester can sign in by hand in the visible Runner browser and then re-run the Inspection in that same browser session.

**Consequences (testable):**
- The re-run Inspection captures elements that were inaccessible before login.
- The system never stores or asks for the tester's credentials.

#### FR-8: Persist Inspections
Every completed or partial Inspection, including its screenshot and Findings, is saved in the Inspection store.

**Consequences (testable):**
- A stored Inspection can be reopened after the application restarts, with identical Findings and screenshot.
- Each Inspection keeps its source URL and capture time so later steps (and later phases) reference exactly what was observed.
- The tester can export an Inspection as structured JSON (the "sample structured inspection output" required for submission).

#### FR-9: Optional tester-driven page exploration *(stretch)*
The tester can move to another page of the same site and inspect it within the same Session. Each page produces its own Inspection.

**Consequences (testable):**
- Exploration mechanics (tester-driven navigation vs. assisted link following) are deferred; see Open Questions.
- Inspections in one Session are listed together and each stays linked to its own page.

### 4.2 Guided Interaction
*Rubric: Basic human interaction (2 pts).*

**Description:** The tester steers the assistant in two independent ways. The Testing goal says *what* to do, as free text the tester can edit at any point in the Session. The Scope says *which* Findings to do it with, built by selecting Findings one by one or by combining group filters, then removing individual elements. Selecting a Finding does not mean testing it. Selection defines Scope; the Testing goal defines what happens to that Scope. When the Testing goal is too vague, or refers to something absent from the page, the assistant issues a Clarification request before acting.

**Functional Requirements:**

#### FR-10: State and edit a Testing goal
The tester can write a Testing goal as free text and edit it at any time during the Session.

**Consequences (testable):**
- The current Testing goal is always visible alongside the Findings.
- Editing the goal keeps the current Scope unchanged, and later assistant requests use the new goal.
- Earlier goals in the Session are kept and remain viewable (goal history), for use by FR-13 and as groundwork for Phase 2 versioning.
- *(Stretch)* The assistant can propose Testing goals as a pick list, grounded in the Inspection's Findings; the tester chooses or ignores them.

#### FR-11: Select individual Findings into Scope
The tester can add or remove a Finding from the Scope by selecting its row in the Findings table.

**Consequences (testable):**
- Each selected Finding gets its own unique color: its table row is highlighted in that color, and its outline on the screenshot uses the same color, so row and element pair up at a glance.
- Colors assigned to selected Findings are visibly different from one another and from the unselected marker style. Colors come from a fixed palette of high-contrast, distinguishable colors; beyond the palette size, colors are reused only with the Finding number shown alongside, so pairing never relies on color alone.
- A counter shows how many Findings are in Scope (e.g. "3 elements selected").
- A side panel lists the Findings in Scope with their key details.
- *(Stretch)* Clicking a screenshot marker toggles that Finding in Scope.

#### FR-12: Refine Scope with combinable group filters
The tester can narrow the Scope with group filters: by container (e.g. only the login form), element type (e.g. only inputs), visibility (include or exclude hidden elements), interaction (only clickable), semantic role (e.g. only buttons), and exclusion (e.g. hide links).

**Consequences (testable):**
- Filters combine with AND logic: "only the login form" + "only inputs" yields inputs inside that form, not every input on the page.
- A live count shows how many Findings match the current filters.
- After applying filters, the tester can still remove individual Findings from the result.
- Filters only operate on recorded Finding data; they never add elements that were not observed.

#### FR-13: Clarify vague or unmatched Testing goals through conversation
When the Testing goal is too vague to act on, or refers to something not present among the Findings, the assistant opens a multi-turn conversation of Clarification requests before producing output. Each question is specific to this website and to what the tester has done in the Session, never a generic question.

**Consequences (testable):**
- Clarification is a conversation, not a single question: the assistant can ask follow-ups based on the tester's previous answers, and continues until the Testing goal is actionable or the tester skips.
- "Actionable" means the assistant's confidence in its understanding of the Testing goal reaches a required threshold. Below the threshold the assistant keeps clarifying; at or above it, the assistant proceeds. The current confidence is always visible to the tester. [ASSUMPTION: how confidence is computed (signals used) and the threshold value are decided during development; see Open Questions.]
- Every Clarification request references Session context: at least one specific Finding, container, or observed page detail, and, where relevant, the tester's earlier actions (current and earlier Testing goals, current Scope, filters applied, earlier answers). Example: "Your Scope has the Email and Password inputs in `form#login`. Should I focus on invalid email formats, empty required fields, or both?" rather than "What do you want to test?"
- The assistant never re-asks a question the tester already answered in the Session.
- The conversation is shown in the interface and kept with the Session, so later assistant requests can use it.
- A goal such as "test this page" triggers a Clarification request that names the page's actual areas (e.g. the observed forms or groups of Findings) as options.
- A goal naming an element not present in the Inspection (e.g. "test the search bar" on a login page) is answered with a Grounded statement that no such element was observed, plus a Clarification request. The assistant never treats a different element as the missing one.
- If the tester skips or dismisses the Clarification request, the assistant generates suggestions grounded only in the Findings in Scope, labeled as suggestions. Skipping is an explicit tester action (e.g. a Skip control), never a timeout.

### 4.3 Grounded Assistant
*Rubric: Feasibility evidence (1 pt, the meaningful model call); carries the product's core principle of evidence-backed accuracy.*

**Description:** In Phase 1 the assistant summarizes the current Scope. The summary helps the tester understand what was selected, what can be tested, and what still needs clarification before execution. It is built only from Findings in Scope, the Testing goal, and Session context. Every response uses a fixed set of sections written in natural language: **Observed**, **Inferred meaning**, **Unverified**, and **Next step**. Every mention of a Finding links to it. Before the tester sees anything, the system checks the response against the Inspection: it validates first, retries automatically second, and blocks unsupported claims as the final safeguard.

**Functional Requirements:**

#### FR-14: Summarize the Scope
The tester can ask the assistant to summarize the current Scope in light of the Testing goal.

**Consequences (testable):**
- The summary covers what was selected, what can be tested with it, and what still needs clarification before execution.
- The summary uses only Findings in Scope, the Testing goal, and Session context (earlier goals, answers, Clarification conversation). It does not use other Findings, outside knowledge of the site, or guesses about unobserved behavior.
- If the Testing goal is not yet actionable (FR-13), the assistant clarifies before summarizing.

**Out of Scope:**
- Test case design, Playwright code generation, and execution (later phases).

#### FR-15: Structured response sections
Every assistant response is organized into the sections Observed, Inferred meaning, Unverified, and Next step, each written in natural language.

**Consequences (testable):**
- Observed contains only Grounded statements about what the Inspection detected.
- Inferred meaning states what the assistant infers the Observed items are for, kept visibly separate from fact (e.g. "these elements appear to belong to a login form") and names the Findings it is based on.
- Unverified lists what cannot yet be confirmed (e.g. "whether authentication works has not been tested").
- Next step suggests what the tester should do next.
- A section with nothing to say is omitted, never shown empty.

#### FR-16: Clickable Evidence links
Every mention of a Finding in an assistant response links to that Finding.

**Consequences (testable):**
- Clicking a mention opens that Finding's detail panel (FR-4) and highlights it in the table and screenshot.
- Every Finding the response references resolves to a real Finding in the Inspection; there are no dangling links.

#### FR-17: Validate, retry, then block unsupported claims
Before showing a response, the system checks it against the Inspection, in three steps.

**Consequences (testable):**
- **Validate:** each response is checked automatically for: correct section structure; references only to Finding IDs that exist in Scope; attributes and values that match the referenced Finding exactly.
- **Retry:** a response that fails validation is regenerated automatically, with the validation errors given back to the model. The retry count is capped and configurable; its default value is decided during development (see Open Questions).
- **Block:** if retries are exhausted, claims that still fail validation are removed. The tester sees the remaining valid content and a notice that some content was withheld because it could not be backed by Evidence. If nothing valid remains, the tester sees that the assistant could not produce a grounded answer and can retry.
- Validation outcomes (passed, retried N times, claims blocked) are recorded with the response and visible to the tester.
- Unsupported claims are never shown as if they were valid.

### 4.4 Model Usage Record
*Rubric: Feasibility evidence (1 pt): record model/version, hardware or API setup, token usage, and response time. Groundwork for Phase 2's per-call usage display and averages.*

**Description:** Every call the system makes to the model produces a Model call record, including automatic retries from FR-17. Each assistant response carries a compact badge summarizing the calls behind it, expandable to show each call. The tester can export all records as JSON, which serves as the usage and timing evidence for submission.

**Functional Requirements:**

#### FR-18: Record every model call
The system creates one Model call record for every model call, including each automatic retry.

**Consequences (testable):**
- Each record contains: model name and version, hardware or API setup (e.g. GPU, VRAM, runtime), prompt tokens, completion tokens, total tokens, response time, timestamp, the Session and assistant response it belongs to, and its validation outcome (passed / failed and retried / claims blocked).
- Retries are separate records, never merged: an assistant response that needed one retry has two records.
- Token counts come from the model runtime's own reporting, not estimates. [ASSUMPTION: the chosen local runtime reports token counts per call.]

#### FR-19: Usage badge on each assistant response
Each assistant response shows a badge summarizing the Model call records behind it.

**Consequences (testable):**
- The badge shows the model, number of calls, total tokens, and total response time (e.g. "qwen3:4b · 2 calls · 1,250 tokens · 6.4 s").
- Expanding the badge lists each call with its own tokens, response time, and validation outcome.

#### FR-20: Export usage records as JSON
The tester can export the Model call records as a JSON file.

**Consequences (testable):**
- The export includes every field from FR-18 for every call in the selected Session.
- The file is valid JSON and is readable without the application.

#### FR-21: Session average response time *(stretch)*
The interface shows the average response time per model call across the current Session.

**Consequences (testable):**
- The average updates after each new model call and counts retries as individual calls.

### 4.5 Architecture and Approval-Gate Design
*Rubric: Architecture and system design (4 pts). The design itself is produced in the architecture document (`bmad-architecture`); this section fixes what it must cover.*

**Description:** The design document explains how the parts of the system fit together for the full workflow, not just Phase 1, so Phase 2 components can be built early on the same foundation.

**Functional Requirements:**

#### FR-22: Component diagram and data flow
The design document provides a component diagram and data flow covering the web interface, model integration (the Agent loop), the Inspection store and state storage, and the isolated Runner.

#### FR-23: Approval gates across the full workflow
The design document names every Approval gate and where it sits: approval of the test plan, review of generated code, approval before executing tests, approval before reruns, and approval before applying maintenance repairs, plus Clarification requests for ambiguous matches.

#### FR-24: Validation points
The design document describes each validation step: assistant output validation (FR-17) in Phase 1, and syntax validation plus verification of locators against observed Findings before execution in Phase 2.

#### FR-25: How later phases use inspection results
The design document shows the path from Inspection to test generation, execution, and maintenance: how stored Findings, Locator candidates, and Finding IDs are reused, and how a rescan is compared against a stored Inspection.

#### FR-26: Resource assumptions
The design document records the selected model, its configuration, the hardware, and practical resource limits (context size, response time, memory).

**Notes (open, to resolve in architecture):** what "isolated" means for the Runner; whether Phase 1 needs its own Approval gate (e.g. the assistant never interacts with the page without approval); single-laptop vs. multi-machine deployment; whether page content may ever leave the machine (free-tier API fallback).

## 5. Cross-Cutting NFRs
- **NFR-1 Grounding:** No assistant content reaches the tester unless it passed validation (FR-17); unsupported claims are never displayed as valid.
- **NFR-2 Local resources:** The system runs on the team's laptop (RTX 3060 Laptop, 6 GB VRAM, 14 GB RAM). Prompts fit the model's context window; Session history and Findings are condensed or selected to fit. [ASSUMPTION: working context of about 4–8k tokens.]
- **NFR-3 Responsiveness:** Assistant responses return within a target time set after the Phase 1 feasibility benchmark. [ASSUMPTION: target defined during development.]
- **NFR-4 Free and secret-free:** No paid model APIs or subscriptions power the system. No API secrets in the repository or submission.
- **NFR-5 Reproducible setup:** Dependencies, setup instructions, and model configuration let another machine run the system from the repository.
- **NFR-6 No agent frameworks:** The Agent loop is hand-written; no CrewAI, LangChain, or similar for model interaction.

## 6. Non-Goals (Phase 1)
- No test case design, Playwright code generation, test execution, rescans, or locator repair. These are Phase 2; Phase 1 only lays groundwork (stored Inspections, goal history, Model call records).
- No autonomous crawling of a site.
- No storing or handling of tester credentials.
- No analysis of network or session behavior (e.g. "HTTP 200 but no session established"); a possible later addition.
- Not a hosted, multi-user product. [ASSUMPTION: one tester at a time on a local machine; confirm in architecture.]

## 7. MVP Scope (Phase 1, Week 9)

### 7.1 In Scope
- FR-1 to FR-8 (inspection, linked views, detail panel, verified locators, failure states, manual login, persistence and JSON export).
- FR-10 to FR-13 (Testing goal with history, selection, group filters, conversational clarification).
- FR-14 to FR-17 (Scope summary, structured sections, Evidence links, validate / retry / block).
- FR-18 to FR-20 (Model call records, usage badge, JSON export).
- FR-22 to FR-26 (design document).
- Submission: design document, runnable source with setup and model configuration, a short demo, a sample structured Inspection (FR-8 export), and usage/timing evidence (FR-20 export).

### 7.2 Stretch
- FR-9 tester-driven multi-page exploration.
- Model-suggested Testing goals (FR-10).
- Selecting by clicking screenshot markers (FR-3, FR-11).
- FR-21 Session average response time.

## 8. Success Metrics
**Primary**
- **SM-1 Rubric coverage:** The demo on the instructor-supplied site shows every Phase 1 rubric item. Validates FR-1 to FR-8, FR-10 to FR-20, FR-22 to FR-26.
- **SM-2 Zero unsupported claims:** No assistant claim shown during the demo lacks Evidence. Validates FR-15 to FR-17.

**Secondary**
- **SM-3 Locator quality:** The top-ranked Locator candidate matches exactly one element for nearly all Findings on the instructor site. [ASSUMPTION: target ≥ 90%.] Validates FR-5.
- **SM-4 Feasibility evidence:** Exported Model call records show model, hardware, tokens, and response time for every call. Validates FR-18, FR-20.

**Counter-metrics (do not optimize)**
- **SM-C1 Raw speed:** Do not cut response time by skipping validation or retries. Counterbalances NFR-3.
- **SM-C2 Volume:** Do not maximize the number of Findings or suggestions at the cost of accuracy. Counterbalances SM-1.

## 9. Open Questions
1. FR-9: exploration mechanics (tester-driven navigation vs. assisted link following).
2. FR-13: how confidence is computed (prefer observable signals over model self-rating) and the threshold value.
3. FR-17: default retry count.
4. FR-22 / 4.5 Notes: meaning of Runner isolation; a Phase 1 Approval gate; deployment shape; whether page content may leave the machine.
5. Frontend framework (Node + TypeScript; framework to be chosen).
6. Model: `qwen3:4b-instruct-2507-q4_K_M` only, measured by the feasibility benchmark (see `docs/resources.md`).

## 10. Assumptions Index
- §4.2 FR-13: confidence method and threshold decided in development.
- §4.4 FR-18: the local runtime reports per-call token counts.
- §5 NFR-2: working context of about 4–8k tokens.
- §5 NFR-3: response-time target set after the benchmark.
- §6: single local tester at a time.
- §8 SM-3: locator uniqueness target ≥ 90%.
