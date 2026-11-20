"""Clarification confidence from observable signals only (AD-16). The model never scores.

score = 0.10 * has_goal
      + 0.35 * references      (goal/answers mention words of recorded Findings or containers, or an f_ id)
      + 0.25 * scope_non_empty
      + 0.30 * names_action    (an action verb such as test, verify, fill, click, sign in)
      - 0.15 * open_ambiguities (unanswered, unskipped clarification turns)
      - 0.30 if unmatched_mentions (an element named in the goal, e.g. "search bar", was not observed;
               descriptive words such as "required fields" or "header links" never count as unmatched)
clipped to [0, 1]; actionable = score >= config clarification.threshold and no unmatched mentions.

Text = the current goal plus the tester's clarification answers. Words are compared
lower-cased with small normalizations (sign in / log in -> login, e-mail -> email).
"""

import re

from contracts import Finding, Inspection, Session
from contracts.models import Model
from pydantic import Field

from app.utils.config import get_config

WEIGHTS = {"has_goal": 0.10, "references": 0.35, "scope_non_empty": 0.25, "names_action": 0.30}
AMBIGUITY_PENALTY = 0.15
UNMATCHED_PENALTY = 0.30

ACTION_VERBS = {
    "test", "verify", "check", "validate", "ensure", "confirm", "try", "submit", "fill", "enter", "type",
    "click", "press", "select", "choose", "login", "register", "signup", "search", "navigate", "open",
    "upload", "reset", "toggle", "logout", "subscribe", "send", "create", "delete", "edit", "update",
}  # fmt: skip
ELEMENT_NOUNS = {
    "bar", "box", "field", "fields", "button", "buttons", "link", "links", "input", "inputs", "menu",
    "dropdown", "form", "checkbox", "checkboxes", "tab", "tabs", "section", "area", "icon", "slider",
    "toggle", "picker", "widget", "modal", "dialog", "table", "list", "textarea", "select", "radio",
}  # fmt: skip
STOPWORDS = {
    "the", "a", "an", "this", "that", "these", "those", "my", "our", "your", "its", "of", "on", "in", "to",
    "for", "with", "without", "and", "or", "all", "every", "each", "some", "any", "page", "site", "website",
    "it", "is", "are", "be", "should", "can", "if", "when", "then", "works", "work", "whole", "entire",
}  # fmt: skip
# Describe an element rather than name it: never "unmatched" ("the required fields", "header links")
QUALIFIERS = {
    "required", "optional", "invalid", "valid", "empty", "hidden", "visible", "disabled", "enabled", "main",
    "primary", "secondary", "top", "bottom", "header", "footer", "other", "first", "last", "new", "input",
    "text", "two", "both", "multiple", "single", "remaining", "wrong", "correct", "long", "short",
}  # fmt: skip
SYNONYMS = {"navigation": "nav", "e": "email", "mail": "email", "pwd": "password", "pass": "password"}
GENERIC_VERBS = {"test", "verify", "check", "validate", "ensure", "confirm", "try"}
GENERIC = STOPWORDS | ELEMENT_NOUNS | GENERIC_VERBS | QUALIFIERS  # never count as a reference to the page
_WORD = re.compile(r"[a-z0-9]+")
_FINDING_ID = re.compile(r"\bf_\d{3,}\b")
_PHRASES = (
    (re.compile(r"\b(sign|log)[\s-]?in\b"), "login"),
    (re.compile(r"\b(sign|log)[\s-]?out\b"), "logout"),
    (re.compile(r"\bsign[\s-]?up\b"), "signup"),
    (re.compile(r"\be-mail\b"), "email"),
)


class ConfidenceSignals(Model):
    has_goal: bool
    references: bool
    scope_non_empty: bool
    names_action: bool
    open_ambiguities: int


class ConfidenceReport(Model):
    score: float = Field(ge=0, le=1)
    actionable: bool
    threshold: float
    signals: ConfidenceSignals
    matched_terms: list[str] = Field(default_factory=list)
    unmatched_mentions: list[str] = Field(default_factory=list, description='e.g. "search bar"')
    containers: list[str] = Field(default_factory=list, description="Observed containers, page areas")


def normalize(text: str) -> str:
    text = text.lower()
    for pattern, replacement in _PHRASES:
        text = pattern.sub(replacement, text)
    return text


def words(text: str) -> list[str]:
    return [SYNONYMS.get(w, w) for w in _WORD.findall(normalize(text))]


def _finding_vocabulary(finding: Finding) -> set[str]:
    texts = [finding.tag, finding.type, finding.role, finding.accessible_name, finding.label, finding.visible_text]
    texts += [finding.container]
    texts += [v for k, v in finding.attributes.items() if k in ("id", "name", "placeholder", "data-testid", "title")]
    texts += list(finding.attributes)  # attribute names: "required", "minlength", ...
    return {w for t in texts if t for w in words(t)} - STOPWORDS


def containers(inspection: Inspection | None) -> list[str]:
    seen: list[str] = []
    for finding in inspection.findings if inspection else []:
        if finding.container and finding.container not in seen:
            seen.append(finding.container)
    return seen


def compute(session: Session, inspection: Inspection | None) -> ConfidenceReport:
    answers = [t.answer for t in session.clarification if t.answer]
    text = " ".join([session.current_goal or "", *answers])
    tokens = words(text)
    vocabulary: set[str] = set()
    known_ids: set[str] = set()
    for finding in inspection.findings if inspection else []:
        vocabulary |= _finding_vocabulary(finding)
        known_ids.add(finding.finding_id)

    matched = sorted({t for t in tokens if t in vocabulary and t not in GENERIC})
    matched += sorted(set(_FINDING_ID.findall(text)) & known_ids)
    unmatched = []
    for previous, word in zip(tokens, tokens[1:], strict=False):
        if word in ELEMENT_NOUNS and previous not in GENERIC | ELEMENT_NOUNS and previous not in vocabulary:
            unmatched.append(f"{previous} {word}")

    signals = ConfidenceSignals(
        has_goal=bool(session.current_goal),
        references=bool(matched),
        scope_non_empty=bool(session.scope.refs),
        names_action=any(t in ACTION_VERBS for t in tokens),
        open_ambiguities=sum(1 for t in session.clarification if t.answer is None and not t.skipped),
    )
    score = sum(w for name, w in WEIGHTS.items() if getattr(signals, name))
    score -= AMBIGUITY_PENALTY * signals.open_ambiguities
    score -= UNMATCHED_PENALTY if unmatched else 0
    score = round(min(1.0, max(0.0, score)), 2)
    threshold = get_config().clarification.threshold
    return ConfidenceReport(
        score=score,
        actionable=score >= threshold and not unmatched,
        threshold=threshold,
        signals=signals,
        matched_terms=matched,
        unmatched_mentions=list(dict.fromkeys(unmatched)),
        containers=containers(inspection),
    )


def normalize_question(text: str) -> str:
    """Comparable form of a clarification question (dedupe: never ask an answered question again)."""
    return " ".join(words(text))
