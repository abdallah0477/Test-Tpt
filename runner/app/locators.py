"""Ranked, verified locator candidates for a Finding (Story 1.6, AD-11, AD-13).

1. `candidates_for()` proposes (strategy, args) pairs in preference order:
   role (+ accessible name), label, test_id, css (attribute based), text.
   XPath and positional selectors (nth-child, nth(), index) are never produced.
2. `verify()` builds the *same* Playwright locator that `render_locator()` prints,
   counts its matches on the live page, then ranks:
   - unique candidates (match_count == 1) keep their preference order and come first;
   - every other candidate is ranked below all unique ones with reliability Low.
   Reliability for unique ones: High for role/label/test_id, Medium for css/text.
"""

import re
from typing import Any

from contracts import Finding, LocatorCandidate, LocatorStrategy, Reliability

LocatorArgs = dict[str, str | bool]

# Roles of form fields that a <label> (or aria-label) can name.
LABELABLE_ROLES = {"textbox", "searchbox", "combobox", "listbox", "checkbox", "radio", "slider", "spinbutton", "switch"}
LABELABLE_TAGS = {"input", "select", "textarea"}
TEXT_TAGS_OR_ROLES = {"a", "button", "link"}
MAX_TEXT = 80
MAX_CSS = 3
SIMPLE_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def css_value(value: str) -> str:
    """Quote a value for a CSS attribute selector: [name="..."]."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def css_candidates(finding: Finding, href: str | None) -> list[str]:
    """Attribute-based CSS selectors, most specific first, at most MAX_CSS."""
    attrs = finding.attributes
    tag = finding.tag
    selectors: list[str] = []
    if attrs.get("id"):
        element_id = attrs["id"]
        selectors.append(f"#{element_id}" if SIMPLE_ID.match(element_id) else f"[id={css_value(element_id)}]")
    if attrs.get("name"):
        selectors.append(f"{tag}[name={css_value(attrs['name'])}]")
    if tag == "a" and href:
        selectors.append(f"a[href={css_value(href)}]")
    if attrs.get("placeholder"):
        selectors.append(f"{tag}[placeholder={css_value(attrs['placeholder'])}]")
    if attrs.get("type"):
        selectors.append(f"{tag}[type={css_value(attrs['type'])}]")
    return selectors[:MAX_CSS]


def candidates_for(finding: Finding, href: str | None = None) -> list[tuple[LocatorStrategy, LocatorArgs]]:
    """Proposed candidates in preference order (not yet verified)."""
    out: list[tuple[LocatorStrategy, LocatorArgs]] = []
    if finding.role:
        args: LocatorArgs = {"role": finding.role}
        if finding.accessible_name:
            args |= {"name": finding.accessible_name, "exact": True}
        out.append((LocatorStrategy.role, args))

    is_field = finding.tag in LABELABLE_TAGS or finding.role in LABELABLE_ROLES
    label_text = finding.label or finding.attributes.get("aria-label")
    if is_field and label_text:
        out.append((LocatorStrategy.label, {"text": label_text, "exact": True}))

    if finding.attributes.get("data-testid"):
        out.append((LocatorStrategy.test_id, {"test_id": finding.attributes["data-testid"]}))

    for selector in css_candidates(finding, href):
        out.append((LocatorStrategy.css, {"selector": selector}))

    text = finding.visible_text
    if text and len(text) <= MAX_TEXT and (finding.tag in TEXT_TAGS_OR_ROLES or finding.role in TEXT_TAGS_OR_ROLES):
        out.append((LocatorStrategy.text, {"text": text, "exact": True}))
    return out


def playwright_locator(page: Any, strategy: LocatorStrategy, args: LocatorArgs) -> Any:
    """The Playwright locator that `contracts.render_locator()` renders for these args."""
    if strategy == LocatorStrategy.role:
        kwargs = {k: args[k] for k in ("name", "exact") if k in args}
        return page.get_by_role(args["role"], **kwargs)
    if strategy == LocatorStrategy.label:
        return page.get_by_label(args["text"], **({"exact": args["exact"]} if "exact" in args else {}))
    if strategy == LocatorStrategy.test_id:
        return page.get_by_test_id(args["test_id"])
    if strategy == LocatorStrategy.css:
        return page.locator(args["selector"])
    return page.get_by_text(args["text"], **({"exact": args["exact"]} if "exact" in args else {}))


def reliability(strategy: LocatorStrategy, match_count: int) -> Reliability:
    if match_count != 1:
        return Reliability.Low
    if strategy in (LocatorStrategy.role, LocatorStrategy.label, LocatorStrategy.test_id):
        return Reliability.High
    return Reliability.Medium


def rank(proposed: list[tuple[LocatorStrategy, LocatorArgs, int]]) -> list[LocatorCandidate]:
    """Unique candidates first (in preference order), then the rest; rank starts at 1."""
    unique = [p for p in proposed if p[2] == 1]
    others = [p for p in proposed if p[2] != 1]
    return [
        LocatorCandidate(
            strategy=strategy, args=args, match_count=count, rank=i, reliability=reliability(strategy, count)
        )
        for i, (strategy, args, count) in enumerate(unique + others, start=1)
    ]


def verify(page: Any, finding: Finding, href: str | None = None) -> list[LocatorCandidate]:
    """Propose, count on the live page, and rank the candidates for one Finding."""
    proposed = []
    for strategy, args in candidates_for(finding, href):
        try:
            count = playwright_locator(page, strategy, args).count()
        except Exception:  # e.g. a selector the engine rejects: treat as matching nothing
            count = 0
        proposed.append((strategy, args, count))
    return rank(proposed)
