# Phase 1 demo script (about 5 minutes)

Shows the brief's Phase 1 demonstration: open a supplied page, inspect its interactive elements, show the findings, let the tester set a goal and choose elements, and have the model summarize the selection grounded in the observed page.

Use the instructor's supplied page if one is given. Otherwise use the bundled signup page below, which works offline.

## Before the demo (not shown)

1. Start Ollama so the containers can reach it (Linux: `OLLAMA_HOST=172.17.0.1:11434 ollama serve`; see README step 3).
2. `docker compose up --build -d` and wait until `docker compose ps` shows all three services healthy.
3. Only for the bundled page: `python3 -m http.server 8088 --bind 172.17.0.1 --directory backend/scripts/bench_pages`.
4. Open http://127.0.0.1:5173 and check that the header says **Model ready (qwen3:4b-instruct-2507-q4_K_M, Ollama …)**. The backend has already warmed the model, so the first answer won't pay the load time.

## 1. Open the supplied page and inspect (≈1 min)

- Enter `http://host.docker.internal:8088/signup.html` (or the supplied URL) and click **Start inspection**.
- **Say:** "Starting an inspection records approval G0 for this origin. The Runner is a locked-down container, and its browser can only reach this site."
- Point at the live browser view: the page opens in a real, visible Chromium. Point at the progress steps (load → extract → locators → screenshot).
- **Say:** "All of this is deterministic code. The model hasn't been called yet."

## 2. Show the findings (≈1 min)

- The numbered screenshot and the Findings table: every input, select, checkbox, radio and button, with its type, accessible name and visibility.
- Click the **Password** Finding. The detail panel shows the exact DOM attributes (`minlength="10"`, `required`, `aria-describedby`), its container, a crop, and **Locator candidates** with live match counts. The best one is `get_by_label("Password")`, and it matches exactly 1 element.
- **Say:** "Locators are verified against the live page. Anything that doesn't match exactly one element is ranked down, and XPath is never suggested."
- Click **Export JSON**: this is the structured inspection output (sample in `docs/samples/inspection.json`).

## 3. Set a vague goal and get a clarification (≈1 min)

- In **Testing goal**, enter `test this page` and click **Set goal**. Leave the Scope empty and click **Summarize Scope**.
- The confidence meter is below the threshold, so the assistant **asks** instead of guessing. Point at the reasons: no element named, empty Scope.
- **Say:** "Confidence is computed by code from observable signals, not from the model's opinion of itself. The workflow stops until I answer or skip."
- Answer: `I want to check the password rules and the confirm-password field.`

## 4. Select elements (≈30 s)

- Tick **Password** and **Confirm password** into the Scope (the colours pair the table rows with the screenshot boxes). Optionally use the filters (type = password) and **Apply to Scope**.
- Refine the goal: `verify the password length rules and the mismatch case`, then **Set goal**. The goal history keeps the earlier version.

## 5. Grounded summary with the usage badge (≈1.5 min)

- Click **Summarize Scope**. The answer arrives in about 4–9 s.
- Walk through the sections:
  - **Observed**: facts quoted from the DOM, e.g. both fields have `minlength="10"` and are `required`. Click an evidence link: it highlights that Finding in the table and on the screenshot.
  - **Inferred meaning**: e.g. passwords shorter than 10 characters should be rejected, labelled as an inference.
  - **Unverified**: e.g. whether a mismatch message is shown, because the page doesn't reveal it until it's submitted.
  - **Next step**: a suggested test, still for the tester to decide.
- **Say:** "Every claim cites a Finding in my Scope, and quoted values are checked against the stored Inspection. A claim that fails validation is retried with the errors fed back, and if it still fails it's withheld with a notice. It's never shown."
- Expand the **usage badge**: model, calls, prompt and completion tokens, response time and load time per attempt, and the validation outcome.
- Click **Export usage**: the model call records as JSON (sample in `docs/samples/model_calls.json`).

## Wrap-up (≈30 s)

- Measured on this laptop: 100% JSON valid on the first attempt and a 100% grounding pass over 16 cases. The p95 per answer is 9.0 s, at 66.5 tokens/s and 3.9 GB of VRAM (`docs/resources.md`).
- Phase 2 builds on the same stored Inspections and approval gates: test plan (G1) → template-generated Page Objects → review (G2) → run (G3) → rescan and repair (G5).

## If something goes wrong live

- **Model not reachable**: Ollama isn't on the bridge address. Restart it with `OLLAMA_HOST` (README, Troubleshooting).
- **Page unreachable**: use `host.docker.internal`, not `localhost`.
- **Slow first answer**: the model was unloaded (idle for more than 30 min). It takes a few seconds to reload, and later calls are fast.
