"""Model benchmark on real Inspections (Story 4.1).

    cd backend
    uv run python scripts/benchmark.py                       # qwen3:4b-instruct-2507-q4_K_M
    uv run python scripts/benchmark.py --regenerate          # re-inspect the pages first

1. Inspections: the bench pages (runner/tests/fixtures/login.html, scripts/bench_pages/
   signup.html and search.html) are served on 127.0.0.1 and inspected through the REAL
   backend path (POST /api/v1/session, POST /api/v1/inspection -> Runner at RUNNER_URL ->
   import). They are stored in an isolated DATA_DIR (default backend/.benchmark/data) and
   reused on later runs. A Runner must be running for the first run (natively:
   `cd runner && RUNNER_HEADLESS=true EXCHANGE_DIR=<dir> uv run uvicorn app.api:app --port 8100`,
   with the same EXCHANGE_DIR given to this script).
2. Cases: Scope-summary cases (goal + Scope). As in the app, a case whose goal is not
   actionable (utils/confidence) runs the clarification prompt instead of the summary.
3. For every model: unload all models, warm up (cold load_ms), then run every case
   through the real utils/agent_loop + utils/model_client, sampling nvidia-smi for VRAM.

Writes docs/benchmark-results.json and the results section of docs/resources.md.
Afterwards the app's default model is loaded again.
"""

import argparse
import asyncio
import functools
import http.server
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))

# The project uses only this model.
DEFAULT_MODELS = ["qwen3:4b-instruct-2507-q4_K_M"]
PAGES = {
    "login": REPO / "runner/tests/fixtures/login.html",
    "signup": BACKEND / "scripts/bench_pages/signup.html",
    "search": BACKEND / "scripts/bench_pages/search.html",
}
RESOURCES = REPO / "docs/resources.md"
RESULTS = REPO / "docs/benchmark-results.json"
START, END = "<!-- benchmark:start -->", "<!-- benchmark:end -->"


# ---------------------------------------------------------------- cases


def _in(container: str):
    return lambda f: (f.container or "") == container or container in (f.container or "")


def _ids(*ids: str):
    return lambda f: f.attributes.get("id") in ids or f.attributes.get("name") in ids


def _tag(*tags: str):
    return lambda f: f.tag in tags


def _all(*preds):
    return lambda f: all(p(f) for p in preds)


def _add_buttons(f) -> bool:
    return f.tag == "button" and (f.accessible_name or "").startswith("Add ")


def _visible(f) -> bool:
    return f.visibility.value == "visible"


@dataclass
class Case:
    name: str
    page: str
    goal: str
    select: object  # Finding -> bool


CASES = [
    Case("login_invalid_email", "login", "test login with an invalid email", _all(_in("form#login"), _visible)),
    Case("login_password_rules", "login", "verify the password length rules", _ids("password")),
    Case("login_remember_submit", "login", "check the Remember me checkbox and the Sign In button", _in("form#login")),
    Case("login_newsletter", "login", "test the newsletter topic field and its submit buttons", _in("newsletter")),
    Case("login_nav_links", "login", "check the navigation links in the header", _all(_tag("a"), _in("nav"))),
    Case("login_vague", "login", "test this page", _visible),
    Case("signup_mismatch", "signup", "test signup with mismatched passwords", _in("form#signup")),
    Case("signup_required", "signup", "verify the required fields on the signup form", _in("form#signup")),
    Case("signup_choices", "signup", "check the country dropdown and the plan radio buttons", _ids("country", "plan")),
    Case("signup_birth_date", "signup", "test the date of birth field", _ids("birth")),
    Case("signup_vague", "signup", "test everything", _visible),
    Case("search_query", "search", "test searching for products with a short query", _in("site-search")),
    Case("search_price_filter", "search", "verify the max price filter limits", _in("form#filters")),
    Case("search_add_to_cart", "search", "check adding results to the cart", _add_buttons),
    Case("search_missing_checkout", "search", "test the checkout button", _visible),
    Case("search_vague", "search", "test it", _visible),
]


# ---------------------------------------------------------------- helpers


class VramSampler(threading.Thread):
    def __init__(self, interval: float = 0.25):
        super().__init__(daemon=True)
        self.interval = interval
        self.peak = 0
        self.samples = 0
        self._halt = threading.Event()

    @staticmethod
    def used_mib() -> int | None:
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout
            return int(out.strip().splitlines()[0])
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            return None

    def run(self) -> None:
        while not self._halt.is_set():
            used = self.used_mib()
            if used is not None:
                self.peak = max(self.peak, used)
                self.samples += 1
            self._halt.wait(self.interval)

    def stop(self) -> int:
        self._halt.set()
        self.join()
        return self.peak


def p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(0.95 * len(ordered) + 0.5) - 1))]


def mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 1) if values else None


def serve_pages() -> tuple[http.server.ThreadingHTTPServer, str]:
    root = Path(tempfile.mkdtemp(prefix="bench-pages-"))
    for name, source in PAGES.items():
        shutil.copy(source, root / f"{name}.html")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


# ---------------------------------------------------------------- inspections


def load_or_generate_inspections(regenerate: bool) -> dict:
    from contracts import Inspection
    from fastapi.testclient import TestClient

    from app.main import app
    from app.utils import store

    index_path = "benchmark/inspections.json"
    if store.exists(index_path) and not regenerate:
        index = store.read_json(index_path)
        return {page: Inspection.model_validate(store.read_json(f"inspections/{ins}/inspection.json"))
                for page, ins in index.items() if page in PAGES}  # fmt: skip

    server, base = serve_pages()
    index, inspections = {}, {}
    try:
        with TestClient(app) as client:
            session_id = client.post("/api/v1/session").json()["session_id"]
            for page in PAGES:
                r = client.post("/api/v1/inspection", json={"session_id": session_id, "url": f"{base}/{page}.html"})
                r.raise_for_status()
                ins = r.json()["inspection_id"]
                for _ in range(600):
                    got = client.get(f"/api/v1/inspection/{ins}")
                    if got.status_code == 200:
                        break
                    time.sleep(0.2)
                inspection = Inspection.model_validate(got.json())
                if inspection.status.value not in ("complete", "partial") or not inspection.findings:
                    raise SystemExit(f"{page}: inspection {inspection.status} ({inspection.reason}); is the Runner up?")
                print(f"inspected {page}: {len(inspection.findings)} findings, browser_ms={inspection.browser_ms}")
                index[page], inspections[page] = ins, inspection
    finally:
        server.shutdown()
    store.update_json(index_path, lambda _: dict(index), expected_rev=None)
    return inspections


# ---------------------------------------------------------------- one model


async def run_model(model: str, inspections: dict) -> dict:
    from contracts import FindingRef, GoalEntry, Scope, Session, new_id

    from app.utils import agent_loop, confidence, model_client
    from app.utils.config import get_config
    from app.v1.assistant import prompts
    from app.v1.assistant.schemas import ClarificationOutput

    os.environ["TPT__MODELS__ASSISTANT__MODEL"] = json.dumps(model)
    get_config.cache_clear()
    model_client.reset()
    agent_loop.clear_cache()

    calls: list = []
    first_parse: dict[str, bool] = {}
    original_call, original_validate = model_client.call, agent_loop.validate

    async def recording_call(*args, **kwargs):
        call = await original_call(*args, **kwargs)
        calls.append(call)
        return call

    def recording_validate(content, schema, scope, check=None):
        result = original_validate(content, schema, scope, check)
        current = calls[-1]
        if current.attempt == 1:
            first_parse[current.response_id] = result[0] is not None
        return result

    model_client.call, agent_loop.validate = recording_call, recording_validate
    try:
        unloaded = await model_client.unload_all()
        baseline_vram = VramSampler.used_mib()
        sampler = VramSampler()
        sampler.start()
        status = await model_client.startup()
        if not status.warm:
            sampler.stop()
            return {"model": model, "error": status.error or "warm-up failed"}
        rows = []
        for case in CASES:
            inspection = inspections[case.page]
            selected = [f for f in inspection.findings if case.select(f)]
            session = Session(
                session_id=new_id("ses"),
                goals=[GoalEntry(text=case.goal)],
                scope=Scope(
                    inspection_id=inspection.inspection_id,
                    refs=[
                        FindingRef(inspection_id=inspection.inspection_id, finding_id=f.finding_id) for f in selected
                    ],
                ),
            )
            report = confidence.compute(session, inspection)
            started = time.monotonic()
            try:
                if report.actionable:
                    kind = "summary"
                    scope = agent_loop.LoopScope(inspection, refs=list(session.scope.refs))
                    result = await agent_loop.run(
                        "benchmark", agent_loop.AnswerSections,
                        prompts.summary_parts(session, selected, inspection), scope,
                        session_id=session.session_id, mode="summary",
                    )  # fmt: skip
                else:
                    kind = "clarification"
                    result = await agent_loop.run(
                        "benchmark", ClarificationOutput,
                        prompts.clarification_parts(session, inspection.findings, inspection, report),
                        agent_loop.LoopScope(inspection), session_id=session.session_id, mode="clarification",
                        check=prompts.clarification_check(session, report),
                        preface=prompts.absence_preface(report),
                    )  # fmt: skip
            except model_client.ModelError as exc:
                rows.append({"case": case.name, "kind": "error", "error": str(exc)})
                continue
            response = result.response
            mine = [c for c in calls if c.response_id == response.response_id]
            sections = response.sections
            rows.append(
                {
                    "case": case.name,
                    "page": case.page,
                    "goal": case.goal,
                    "kind": kind,
                    "confidence": report.score,
                    "scope_size": len(selected),
                    "first_attempt_json_valid": first_parse.get(response.response_id, False),
                    "outcome": response.validation.outcome.value,
                    "retries": response.validation.retries,
                    "blocked_count": response.validation.blocked_count,
                    "calls": len(mine),
                    "response_ms_per_call": [c.response_ms for c in mine],
                    "answer_ms": sum(c.response_ms or 0 for c in mine),
                    "wall_ms": int((time.monotonic() - started) * 1000),
                    "prompt_tokens": sum(c.prompt_tokens or 0 for c in mine),
                    "completion_tokens": sum(c.completion_tokens or 0 for c in mine),
                    "eval_ms": sum(c.eval_ms or 0 for c in mine),
                    "items": {
                        k: len(getattr(sections, k)) for k in ("observed", "inferred", "unverified", "next_step")
                    },
                    "sample": next(
                        (i.text for k in ("observed", "next_step", "unverified") for i in getattr(sections, k)), None
                    ),
                }
            )
            print(f"  {model} {case.name}: {kind} {rows[-1]['outcome']} retries={rows[-1]['retries']} "
                  f"{rows[-1]['answer_ms']} ms")  # fmt: skip
        peak = sampler.stop()
    finally:
        model_client.call, agent_loop.validate = original_call, original_validate

    ok = [r for r in rows if r["kind"] != "error"]
    per_call = [ms for r in ok for ms in r["response_ms_per_call"] if ms is not None]
    gen_tps = [r["completion_tokens"] / (r["eval_ms"] / 1000) for r in ok if r["eval_ms"]]
    e2e_tps = [r["completion_tokens"] / (r["answer_ms"] / 1000) for r in ok if r["answer_ms"]]
    return {
        "model": model,
        "previously_loaded": unloaded,
        "cold_load_ms": status.load_ms,
        "baseline_vram_mib": baseline_vram,
        "peak_vram_mib": peak or None,
        "cases": len(rows),
        "errors": len(rows) - len(ok),
        "first_attempt_json_valid_rate": round(sum(r["first_attempt_json_valid"] for r in ok) / len(ok), 3)
        if ok
        else None,
        "grounding_pass_rate": round(sum(r["outcome"] == "passed" for r in ok) / len(ok), 3) if ok else None,
        "mean_retries": mean([r["retries"] for r in ok]),
        "mean_response_ms_per_call": mean(per_call),
        "p95_response_ms_per_call": p95(per_call),
        "mean_answer_ms": mean([r["answer_ms"] for r in ok]),
        "p95_answer_ms": p95([r["answer_ms"] for r in ok]),
        "generation_tokens_per_s": mean(gen_tps),
        "end_to_end_tokens_per_s": mean(e2e_tps),
        "rows": rows,
    }


# ---------------------------------------------------------------- report


def _fmt(value, suffix="") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.1f}{suffix}"
    return f"{value:,}{suffix}"


def render_markdown(results: dict) -> str:
    lines = [
        START,
        f"## Benchmark results ({results['run_at']})",
        "",
        f"{len(CASES)} cases on {len(results['inspections'])} real Inspections "
        f"({', '.join(f'{p}: {n} Findings' for p, n in results['inspections'].items())}); "
        "Ollama "
        f"{results['ollama_version']}, num_ctx {results['num_ctx']}, temperature {results['temperature']}, "
        f"max_retries {results['max_retries']}. Generated by `backend/scripts/benchmark.py`; raw data in "
        "`docs/benchmark-results.json`.",
        "",
        "| Model | 1st-attempt JSON valid | Grounding pass | Mean retries | Mean / p95 per call (ms) "
        "| Mean / p95 per answer (ms) | Gen tokens/s | Cold load (ms) | Peak VRAM (MiB) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for m in results["models"]:
        if "error" in m:
            lines.append(f"| `{m['model']}` | error: {m['error']} | | | | | | | |")
            continue
        lines.append(
            f"| `{m['model']}` | {m['first_attempt_json_valid_rate']:.0%} | {m['grounding_pass_rate']:.0%} "
            f"| {_fmt(m['mean_retries'])} "
            f"| {_fmt(m['mean_response_ms_per_call'])} / {_fmt(m['p95_response_ms_per_call'])} "
            f"| {_fmt(m['mean_answer_ms'])} / {_fmt(m['p95_answer_ms'])} | {_fmt(m['generation_tokens_per_s'])} "
            f"| {_fmt(m['cold_load_ms'])} | {_fmt(m['peak_vram_mib'])} |"
        )
    lines += [
        "",
        "- *Grounding pass*: the answer passed validation (schema, refs exist and are in Scope, quoted values "
        "match) without any claim being blocked, after at most 2 retries.",
        "- *Per answer*: the model time of all attempts behind one response (retries included), excluding load.",
        "- *Gen tokens/s*: completion tokens / Ollama `eval_duration` (generation only).",
        "- *Peak VRAM*: whole-GPU `nvidia-smi` memory.used while the model ran (includes the desktop's share; "
        f"baseline before loading was ~{results['models'][0].get('baseline_vram_mib', 'n/a')} MiB).",
        f"- **Proposed NFR-3 target:** {results['nfr3_proposal']}",
        END,
    ]
    return "\n".join(lines)


TEMPLATE = """# Resources and model benchmark

Measured on the team laptop. Regenerate the results section with
`cd backend && uv run python scripts/benchmark.py` (it rewrites only the part between the markers).

## Hardware and runtime

| Item | Value |
|---|---|
| GPU | NVIDIA RTX 3060 Laptop, 6 GB VRAM |
| CPU | Intel Core i7-11800H |
| RAM | 14 GB |
| Model runtime | Ollama {ollama} (native on the host, one model loaded at a time, `OLLAMA_NUM_PARALLEL=1`) |
| Default model | `qwen3:4b-instruct-2507-q4_K_M` (Q4_K_M, ~2.5 GB), think=false |
| Context | num_ctx 8192, num_predict 1536 reserved for output |
| Keep-alive | 30m (the backend warms the model at startup) |

## Practical limits

- One model fits in VRAM at a time; switching models costs a cold load (see the table). Keep both roles on
  the same model in Phase 1.
- Prompts are budgeted to num_ctx 8192 minus 1536 output tokens; Findings in Scope come first, so very large
  Scopes (roughly 60+ condensed Findings) get truncated with a note in the prompt.
- Calls are serialized; a second request waits (`wait_ms` in the usage records).
- Small models do not reliably copy long ids, so the model cites Findings by `finding_id` only and the backend
  binds them to the Scope's Inspection.

## Cloud fallback (off by default)

`[cloud] enabled = false`. If enabled, the key comes from `.env` only (`GROQ_API_KEY`) and calls are
throttled to `rpm_limit` / `tpm_limit` from `config.toml` (defaults 30 RPM, 6000 TPM). Groq free-tier limits
are **per model**; a typical sample is 30 requests/min, 8,000 tokens/min and 200,000 tokens/day, but they
change: verify them on the Groq console before a demo and update `config.toml`.

"""


def write_docs(results: dict) -> None:
    RESULTS.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    block = render_markdown(results)
    if RESOURCES.exists() and START in RESOURCES.read_text(encoding="utf-8"):
        text = RESOURCES.read_text(encoding="utf-8")
        before, rest = text.split(START, 1)
        after = rest.split(END, 1)[1] if END in rest else ""
        RESOURCES.write_text(before + block + after, encoding="utf-8")
    else:
        RESOURCES.write_text(TEMPLATE.format(ollama=results["ollama_version"]) + block + "\n", encoding="utf-8")


def propose_nfr3(models: list[dict]) -> str:
    default = next((m for m in models if m["model"] == DEFAULT_MODELS[0] and "error" not in m), None)
    if default is None or default["p95_answer_ms"] is None:
        return "n/a (the default model did not run)"
    seconds = default["p95_answer_ms"] / 1000
    target = max(5, int(-(-seconds * 1.25 // 5) * 5))  # p95 + 25% headroom, rounded up to 5 s
    return (
        f"a validated Scope summary within {target} s at p95 with the default model on this laptop, model warm "
        f"(measured p95 {seconds:.1f} s per answer incl. retries; +25% headroom). Cold start adds the load time."
    )


# ---------------------------------------------------------------- main


async def main_async(args) -> None:
    from app.utils import model_client
    from app.utils.config import get_config

    inspections = load_or_generate_inspections(args.regenerate)
    models = []
    for model in args.models:
        print(f"model {model}")
        models.append(await run_model(model, inspections))
    config = get_config()
    results = {
        "run_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": {"gpu": "RTX 3060 Laptop 6GB", "cpu": "i7-11800H", "ram_gb": 14, "os": platform.platform()},
        "ollama_version": model_client.status().version,
        "num_ctx": config.models.assistant.num_ctx,
        "num_predict": config.models.assistant.num_predict,
        "temperature": config.models.assistant.temperature,
        "max_retries": config.assistant.max_retries,
        "inspections": {p: len(i.findings) for p, i in inspections.items()},
        "cases": [{"name": c.name, "page": c.page, "goal": c.goal} for c in CASES],
        "models": models,
    }
    results["nfr3_proposal"] = propose_nfr3(models)
    write_docs(results)

    # leave the app's default model loaded
    os.environ.pop("TPT__MODELS__ASSISTANT__MODEL", None)
    get_config.cache_clear()
    model_client.reset()
    await model_client.unload_all()
    status = await model_client.startup()
    print(f"default model reloaded: {status.model} warm={status.warm}")
    print(render_markdown(results))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--data-dir", default=str(BACKEND / ".benchmark/data"))
    parser.add_argument("--exchange-dir", default=str(BACKEND / ".benchmark/exchange"))
    parser.add_argument("--regenerate", action="store_true", help="inspect the bench pages again")
    args = parser.parse_args()
    os.environ["DATA_DIR"] = str(Path(args.data_dir).resolve())
    os.environ["EXCHANGE_DIR"] = str(Path(args.exchange_dir).resolve())
    os.environ["TPT__OLLAMA__WARMUP"] = "false"  # the script warms each model itself
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
