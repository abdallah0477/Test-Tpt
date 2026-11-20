"""Prompts of v1/assistant, built with utils/prompting (AD-10).

Feature-written text (instructions, task) is trusted; all Session and page content
goes into data blocks.
"""

from contracts import Finding, Inspection, ResponseItem, Session

from app.utils import confidence, prompting
from app.utils.confidence import ConfidenceReport

SECTION_RULES = (
    "Sections: `observed` = facts visible in the findings data, each citing the FindingRefs it is about; "
    "`inferred` = what those facts probably mean for testing, citing refs; `unverified` = things that cannot be "
    "confirmed from the data; `next_step` = what the tester could do next. Use only the findings data and the "
    "session data. Never mention elements that are not in the findings data and never use outside knowledge of "
    "the site. Write short natural-language sentences."
)

SUMMARY_INSTRUCTIONS = (
    "Summarise the tester's Scope (the Findings in the findings data) in light of the Testing goal. " + SECTION_RULES
)

SUGGESTION_INSTRUCTIONS = (
    "Suggest concrete tests for the Findings in the findings data, grounded only in their observed attributes "
    "(e.g. required, type, pattern, maxlength, disabled). Put each suggestion in `next_step`, citing the refs it "
    "uses; put the facts the suggestions rely on in `observed`. These are suggestions, not facts. " + SECTION_RULES
)

CLARIFICATION_INSTRUCTIONS = (
    "The Testing goal is not yet clear enough to act on. Ask exactly ONE specific clarification question in "
    "`questions`. The question must be about this page: cite the FindingRefs it is about in `refs` and/or list "
    "observed page areas from the page_areas data in `containers` as options. Build on the tester's earlier "
    "answers, goals, Scope and filters in the session data; never ask a question that was already asked. If the "
    "goal names an element listed in unmatched_mentions, do not pick a different element in its place: ask which "
    "observed element or area the tester means. Put grounded facts that motivate the question in `observed` "
    "(each citing refs), or leave it empty."
)


def history(session: Session) -> list[str]:
    """Condensed Session context, oldest first."""
    lines = [f"earlier goal: {g.text}" for g in session.goals[:-1]]
    for turn in session.clarification:
        if turn.answer is not None:
            lines.append(f"asked: {turn.question} | tester answered: {turn.answer}")
        elif turn.skipped:
            lines.append(f"asked: {turn.question} | tester skipped")
        else:
            lines.append(f"asked: {turn.question} | not answered yet")
    return lines


def _session_data(session: Session) -> dict:
    return {
        "scope": [r.finding_id for r in session.scope.refs],
        "active_filters": session.filters.model_dump(exclude_defaults=True),
    }


def summary_parts(session: Session, findings: list[Finding], inspection: Inspection) -> prompting.PromptParts:
    return prompting.PromptParts(
        instructions=SUMMARY_INSTRUCTIONS,
        task="Summarise the Scope now as JSON.",
        inspection_id=inspection.inspection_id,
        findings=findings,
        goal=session.current_goal,
        history=history(session),
        extra={"session": _session_data(session)},
    )


def suggestion_parts(session: Session, findings: list[Finding], inspection: Inspection) -> prompting.PromptParts:
    return prompting.PromptParts(
        instructions=SUGGESTION_INSTRUCTIONS,
        task="Give your testing suggestions now as JSON.",
        inspection_id=inspection.inspection_id,
        findings=findings,
        goal=session.current_goal,
        history=history(session),
        extra={"session": _session_data(session)},
    )


def clarification_parts(
    session: Session, findings: list[Finding], inspection: Inspection, report: ConfidenceReport
) -> prompting.PromptParts:
    return prompting.PromptParts(
        instructions=CLARIFICATION_INSTRUCTIONS,
        task="Ask your one clarification question now as JSON.",
        inspection_id=inspection.inspection_id,
        findings=findings,
        goal=session.current_goal or "(no goal written yet)",
        history=history(session),
        extra={
            "session": _session_data(session),
            "page_areas": report.containers,
            "unmatched_mentions": report.unmatched_mentions,
        },
    )


def absence_preface(report: ConfidenceReport) -> dict[str, list[ResponseItem]]:
    """Backend-authored, deterministic statements: named elements that were not observed."""
    items = [
        ResponseItem(text=f'No element matching "{mention}" was observed in this Inspection.')
        for mention in report.unmatched_mentions
    ]
    return {"observed": items} if items else {}


def clarification_check(session: Session, report: ConfidenceReport):
    """Extra rules for clarification answers: grounded in context, never a repeat, areas named when vague."""
    asked = {confidence.normalize_question(t.question) for t in session.clarification}
    areas = set(report.containers)
    vague = not report.signals.references and not report.unmatched_mentions and bool(areas)  # e.g. "test this page"

    def check(output) -> list[tuple[str | None, int | None, str]]:
        problems: list[tuple[str | None, int | None, str]] = []
        if not output.questions:
            problems.append((None, None, "ask exactly one clarification question in `questions`"))
        for index, question in enumerate(output.questions):
            unknown = [c for c in question.containers if c not in areas]
            if unknown:
                problems.append(("questions", index, f"containers {unknown} were not observed; use {sorted(areas)}"))
            named = [c for c in areas if c in question.text] + [c for c in question.containers if c in areas]
            if not question.refs and not named:
                problems.append(("questions", index, "the question must cite a FindingRef or name an observed area"))
            if confidence.normalize_question(question.text) in asked:
                problems.append(("questions", index, "this question was already asked; ask about something new"))
            if vague and not named:
                problems.append(("questions", index, f"offer the observed page areas as options: {sorted(areas)}"))
        return problems

    return check
