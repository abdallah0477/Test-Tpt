"""Story 1.5: extraction on the login fixture (uses pytest-playwright's headless `page`)."""

from app.extract import extract_findings


def load(page, base_url, path="/login.html"):
    page.set_viewport_size({"width": 1280, "height": 800})
    page.goto(base_url + path)
    findings, raw, stats = extract_findings(page)
    return findings, raw, stats


def by_id(findings):
    return {f.finding_id: f for f in findings}


def test_counts_and_dom_order(page, base_url):
    findings, _, stats = load(page, base_url)
    assert [f.finding_id for f in findings] == [f"f_{i:03d}" for i in range(1, 17)]
    assert [f.tag for f in findings] == [
        "a", "a", "a",                         # nav links (one off-screen)
        "input", "input", "input", "input",    # email, password, hidden csrf, remember
        "button", "button",                    # Sign In, disabled Clear
        "input", "button", "button",           # newsletter topic + two Submit
        "div", "div", "a", "a",                # role=tab, role=button, forgot, terms
    ]  # fmt: skip
    assert stats == {"errors": 0, "frames": 0}


def test_exact_attributes(page, base_url):
    f = by_id(load(page, base_url)[0])
    assert f["f_004"].attributes == {
        "id": "email",
        "name": "email",
        "type": "email",
        "placeholder": "you@example.com",
        "required": "",
    }
    assert f["f_005"].attributes == {
        "id": "password",
        "name": "password",
        "type": "password",
        "minlength": "8",
        "maxlength": "64",
        "required": "",
    }
    assert f["f_006"].attributes == {"type": "hidden", "name": "csrf"}  # value is not an observed field
    assert f["f_008"].attributes == {"type": "submit", "data-testid": "login-submit"}
    assert f["f_009"].attributes == {"type": "reset", "disabled": ""}
    assert f["f_010"].attributes == {"name": "topic", "aria-label": "Topic", "pattern": "[a-z]+"}
    assert f["f_013"].attributes == {"aria-selected": "true", "id": "tab-a"}


def test_names_labels_roles(page, base_url):
    f = by_id(load(page, base_url)[0])
    assert (f["f_004"].role, f["f_004"].accessible_name, f["f_004"].label) == (
        "textbox",
        "Email address",
        "Email address",
    )
    assert (f["f_005"].role, f["f_005"].label) == (None, "Password")  # password inputs have no ARIA role
    assert (f["f_007"].role, f["f_007"].label) == ("checkbox", "Remember me")
    assert (f["f_008"].role, f["f_008"].accessible_name, f["f_008"].visible_text) == ("button", "Sign In", "Sign In")
    assert (f["f_010"].accessible_name, f["f_010"].label) == ("Topic", None)
    assert (f["f_013"].role, f["f_013"].accessible_name) == ("tab", "Overview")
    assert (f["f_014"].role, f["f_014"].accessible_name, f["f_014"].visible_text) == ("button", "Help", "?")
    assert f["f_006"].role is None and f["f_006"].accessible_name is None


def test_containers(page, base_url):
    findings = load(page, base_url)[0]
    assert [f.container for f in findings] == (
        ["nav#primary"] * 3 + ["form#login"] * 6 + ["form[name=newsletter]"] * 3 + ["main"] * 3 + ["footer"]
    )


def test_visibility(page, base_url):
    f = by_id(load(page, base_url)[0])
    hidden = {k for k, v in f.items() if v.visibility == "hidden"}
    assert hidden == {"f_003", "f_006"}  # off-screen skip link, type=hidden
    assert f["f_006"].bbox is None
    assert f["f_009"].visibility == "visible"  # disabled is an attribute, not a visibility state
    assert f["f_004"].bbox is not None and f["f_004"].bbox.width > 0


def test_fingerprint(page, base_url):
    fp = by_id(load(page, base_url)[0])["f_008"].fingerprint
    assert fp.model_dump() == {
        "role": "button",
        "accessible_name": "Sign In",
        "tag": "button",
        "type": "submit",
        "container": "form#login",
        "id": None,
        "name": None,
        "data_testid": "login-submit",
        "label": None,
    }


def test_dom_snippet(page, base_url):
    f = by_id(load(page, base_url)[0])
    assert f["f_004"].dom_snippet.startswith('<input id="email"')
    assert len(f["f_015"].dom_snippet) <= 501


def test_deterministic(page, base_url):
    first = [f.model_dump() for f in load(page, base_url)[0]]
    second = [f.model_dump() for f in load(page, base_url)[0]]
    assert first == second


def test_inaccessible_when_covered(page, base_url):
    findings = load(page, base_url, "/overlay.html")[0]
    assert [(f.finding_id, f.visibility) for f in findings] == [("f_001", "inaccessible")]
