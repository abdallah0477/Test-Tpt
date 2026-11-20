"""Story 1.6: ranked, verified locator candidates."""

import re

from contracts import LocatorStrategy

from app.extract import extract_findings
from app.locators import css_value, rank
from app.locators import verify as verify_locators


def findings_with_locators(page, base_url):
    page.goto(base_url + "/login.html")
    findings, raw, _ = extract_findings(page)
    for finding, element in zip(findings, raw, strict=True):
        finding.locators = verify_locators(page, finding, element.get("href"))
    return {f.finding_id: f for f in findings}


def test_two_identical_submit_buttons(page, base_url):
    f = findings_with_locators(page, base_url)
    plain, with_testid = f["f_011"], f["f_012"]

    role = next(c for c in plain.locators if c.strategy == "role")
    assert role.args == {"role": "button", "name": "Submit", "exact": True}
    assert role.match_count == 2 and role.reliability == "Low"
    assert all(c.match_count != 1 and c.reliability == "Low" for c in plain.locators)

    best = with_testid.locators[0]
    assert (best.strategy, best.expr, best.match_count, best.reliability) == (
        "test_id",
        'page.get_by_test_id("newsletter-submit-2")',
        1,
        "High",
    )
    assert [c.rank for c in with_testid.locators] == [1, 2, 3, 4]
    assert all(c.match_count == 2 for c in with_testid.locators[1:])


def test_preference_order_and_reliability(page, base_url):
    email = findings_with_locators(page, base_url)["f_004"]
    assert [(c.strategy.value, c.reliability.value) for c in email.locators] == [
        ("role", "High"),
        ("label", "High"),
        ("css", "Medium"),
        ("css", "Medium"),
        ("css", "Medium"),
    ]
    assert email.locators[0].expr == 'page.get_by_role("textbox", name="Email address", exact=True)'
    assert email.locators[2].expr == 'page.locator("#email")'


def test_never_xpath_or_positional(page, base_url):
    for finding in findings_with_locators(page, base_url).values():
        for c in finding.locators:
            assert "xpath" not in c.expr and "//" not in c.expr.replace("://", "")
            assert not re.search(r"nth|:first|:last|\.first|\.last|>>", c.expr)


def test_match_count_equals_rendered_expression(page, base_url):
    """The count we store is the count of the exact Playwright code we show."""
    for finding in findings_with_locators(page, base_url).values():
        for c in finding.locators:
            assert eval(c.expr, {"page": page}).count() == c.match_count, c.expr  # noqa: S307


def test_rank_puts_non_unique_below_unique():
    ranked = rank(
        [
            (LocatorStrategy.role, {"role": "button", "name": "Go", "exact": True}, 3),
            (LocatorStrategy.css, {"selector": "#go"}, 1),
            (LocatorStrategy.text, {"text": "Go", "exact": True}, 0),
            (LocatorStrategy.test_id, {"test_id": "go"}, 1),
        ]
    )
    assert [(c.strategy.value, c.rank, c.reliability.value) for c in ranked] == [
        ("css", 1, "Medium"),
        ("test_id", 2, "High"),
        ("role", 3, "Low"),
        ("text", 4, "Low"),
    ]


def test_css_value_escaping():
    assert css_value('a "quoted" \\ value') == '"a \\"quoted\\" \\\\ value"'
