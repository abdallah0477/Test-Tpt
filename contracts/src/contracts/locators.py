"""render_locator(): the only code that turns a locator into Playwright Python text.

Every value placed into code goes through `py_literal()` (AD-13 escaping rule).
"""

import json
from collections.abc import Mapping
from typing import Any

# Allowed args per strategy: (required keys, optional keys)
STRATEGY_ARGS: dict[str, tuple[set[str], set[str]]] = {
    "role": ({"role"}, {"name", "exact"}),
    "label": ({"text"}, {"exact"}),
    "test_id": ({"test_id"}, set()),
    "css": ({"selector"}, set()),
    "text": ({"text"}, {"exact"}),
}


def py_literal(value: Any) -> str:
    """Return a safe Python literal for a str, bool, int or None."""
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        # Prefer double quotes (JSON escaping is valid Python); fall back to
        # repr() when the text contains a double quote, e.g. CSS attribute selectors.
        if '"' in value:
            return repr(value)
        return json.dumps(value, ensure_ascii=False)
    raise TypeError(f"cannot render {type(value).__name__} as a locator argument")


def check_args(strategy: str, args: Mapping[str, Any]) -> None:
    """Raise ValueError if `args` don't fit `strategy`."""
    if strategy not in STRATEGY_ARGS:
        raise ValueError(f"unknown locator strategy: {strategy!r}")
    required, optional = STRATEGY_ARGS[strategy]
    missing = required - args.keys()
    extra = args.keys() - required - optional
    if missing:
        raise ValueError(f"{strategy} locator is missing args: {sorted(missing)}")
    if extra:
        raise ValueError(f"{strategy} locator has unknown args: {sorted(extra)}")
    for key in required:
        if not isinstance(args[key], str) or not args[key]:
            raise ValueError(f"{strategy} locator arg {key!r} must be a non-empty string")
    if "exact" in args and not isinstance(args["exact"], bool):
        raise ValueError("'exact' must be a bool")
    if "name" in args and not isinstance(args["name"], str):
        raise ValueError("'name' must be a string")


def render_locator(candidate: Any, page_var: str = "page") -> str:
    """Render a LocatorCandidate (or a {strategy, args} mapping) as Playwright Python.

    Examples:
        page.get_by_role("button", name="Sign In")
        page.get_by_label("Password")
        page.get_by_test_id("login-submit")
        page.locator('button[type="submit"]')
        page.get_by_text("Forgot password?")
    """
    if isinstance(candidate, Mapping):
        strategy, args = candidate["strategy"], candidate["args"]
    else:
        strategy, args = candidate.strategy, candidate.args
    strategy = getattr(strategy, "value", strategy)
    check_args(strategy, args)

    def kwargs(*names: str) -> str:
        return "".join(f", {n}={py_literal(args[n])}" for n in names if n in args)

    if strategy == "role":
        return f"{page_var}.get_by_role({py_literal(args['role'])}{kwargs('name', 'exact')})"
    if strategy == "label":
        return f"{page_var}.get_by_label({py_literal(args['text'])}{kwargs('exact')})"
    if strategy == "test_id":
        return f"{page_var}.get_by_test_id({py_literal(args['test_id'])})"
    if strategy == "css":
        return f"{page_var}.locator({py_literal(args['selector'])})"
    return f"{page_var}.get_by_text({py_literal(args['text'])}{kwargs('exact')})"
