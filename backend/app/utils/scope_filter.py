"""apply_filters(): group filters over recorded Findings (Story 2.3, FR-12).

Semantics (the frontend mirrors these for live counts):
- All active criteria are combined with AND. An empty list / None criterion does not filter.
- container:      Finding.container == value (exact string, e.g. "form#login").
- element_types:  Finding.tag or Finding.type is in the list (case-insensitive), e.g. ["input"], ["checkbox"].
- include_hidden: False keeps only Findings with visibility "visible" (drops hidden and inaccessible).
- only_clickable: keeps Findings a user can click (see is_clickable) that are not disabled.
- roles:          Finding.role is in the list (case-insensitive).
- exclude_types:  drops Findings whose tag or type is in the list.
- exclude_roles:  drops Findings whose role is in the list.
The result is a subset of the given Findings in their original order: filters
only ever select recorded Findings and never add anything.
"""

from collections.abc import Iterable

from contracts import Finding, ScopeFilters, Visibility

CLICKABLE_TAGS = {"button", "a", "summary", "select", "option"}
CLICKABLE_INPUT_TYPES = {"button", "submit", "reset", "checkbox", "radio", "image", "file"}
CLICKABLE_ROLES = {"button", "link", "checkbox", "radio", "menuitem", "tab", "switch", "option", "combobox"}


def _lower(values: Iterable[str]) -> set[str]:
    return {v.strip().lower() for v in values if v.strip()}


def _kinds(finding: Finding) -> set[str]:
    return {k.lower() for k in (finding.tag, finding.type) if k}


def is_clickable(finding: Finding) -> bool:
    if "disabled" in finding.attributes or finding.attributes.get("aria-disabled") == "true":
        return False
    tag = finding.tag.lower()
    role = (finding.role or "").lower()
    if tag == "input":
        return (finding.type or "text").lower() in CLICKABLE_INPUT_TYPES
    return tag in CLICKABLE_TAGS or role in CLICKABLE_ROLES


def matches(finding: Finding, filters: ScopeFilters) -> bool:
    if filters.container is not None and filters.container.strip() and finding.container != filters.container.strip():
        return False
    types = _lower(filters.element_types)
    if types and not (_kinds(finding) & types):
        return False
    if not filters.include_hidden and finding.visibility is not Visibility.visible:
        return False
    if filters.only_clickable and not is_clickable(finding):
        return False
    roles = _lower(filters.roles)
    if roles and (finding.role or "").lower() not in roles:
        return False
    if _kinds(finding) & _lower(filters.exclude_types):
        return False
    if finding.role and finding.role.lower() in _lower(filters.exclude_roles):
        return False
    return True


def apply_filters(findings: Iterable[Finding], filters: ScopeFilters) -> list[Finding]:
    return [f for f in findings if matches(f, filters)]
