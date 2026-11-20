"""Deterministic extraction of interactive elements as Findings (Story 1.5, AD-11).

All of the work happens in one JavaScript function evaluated in the page. No
model is involved: the same DOM always gives the same Findings.

Which elements: input, textarea, select, button, a[href], and any element whose
`role` is an interactive ARIA role (INTERACTIVE_ROLES). Open shadow roots are
walked in place; iframes are not entered (they are counted instead).

`finding_id` is f_001, f_002 ... in DOM order (shadow content right after its host).

Visibility:
- hidden:       not rendered for a sighted user. `type=hidden`, `hidden` attribute,
                display:none, visibility:hidden/collapse, opacity 0 (on the element or
                an ancestor), zero width or height, or entirely outside the page
                (scrolled off to the left/top, e.g. `left:-9999px`).
- inaccessible: rendered, but a user cannot reach it: inside an `inert` subtree, or
                covered by another element at its centre (e.g. a modal overlay or
                cookie banner). The cover check runs only for elements whose centre
                lies in the first viewport, because elementFromPoint only sees the
                viewport and we never scroll during extraction.
- visible:      everything else.

Container (one format, AD-11): the nearest form owner -> `form#id`, `form[name=x]`
or `form`; otherwise the nearest landmark -> `nav`, `main`, `header`, `footer`,
`aside`, `dialog`, `section` (with `#id` when it has one, e.g. `nav#primary`), or an
element with a landmark role -> `div[role=search]` (`div#id` when it has an id).
"""

from typing import Any

from contracts import BBox, Finding, Fingerprint, Visibility

INTERACTIVE_ROLES = [
    "button",
    "link",
    "checkbox",
    "radio",
    "tab",
    "menuitem",
    "menuitemcheckbox",
    "menuitemradio",
    "switch",
    "combobox",
    "textbox",
    "searchbox",
    "option",
    "slider",
    "spinbutton",
]

# Attributes copied into Finding.attributes, exactly as in the DOM (plus every aria-*).
KEPT_ATTRIBUTES = [
    "id",
    "name",
    "type",
    "placeholder",
    "required",
    "disabled",
    "pattern",
    "minlength",
    "maxlength",
    "data-testid",
]

SNIPPET_MAX = 500

EXTRACT_JS = r"""
({roles, keptAttributes, snippetMax}) => {
  const SELECTOR = ['input', 'textarea', 'select', 'button', 'a[href]',
                    ...roles.map(r => `[role="${r}"]`)].join(',');
  const LANDMARK_TAGS = ['nav', 'main', 'header', 'footer', 'aside', 'dialog', 'section'];
  const LANDMARK_ROLES = ['navigation', 'main', 'banner', 'contentinfo', 'complementary',
                          'region', 'search', 'form', 'dialog', 'alertdialog'];

  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const orNull = s => (s === '' || s === undefined ? null : s);

  // ---- walk the DOM (and open shadow roots) in document order
  const elements = [];
  let frames = 0;
  function walk(root) {
    for (const el of root.children) {
      if (el.matches(SELECTOR)) elements.push(el);
      if (el.tagName === 'IFRAME' || el.tagName === 'FRAME') {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0 && getComputedStyle(el).visibility === 'visible') frames += 1;
      }
      if (el.shadowRoot) walk(el.shadowRoot);
      walk(el);
    }
  }
  walk(document);

  // ---- parent that also steps out of a shadow root to its host
  const parentOf = el => el.parentElement || (el.getRootNode() instanceof ShadowRoot ? el.getRootNode().host : null);

  // ---- role
  function implicitRole(el) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'button') return 'button';
    if (tag === 'a') return el.hasAttribute('href') ? 'link' : null;
    if (tag === 'textarea') return 'textbox';
    if (tag === 'select') return (el.multiple || el.size > 1) ? 'listbox' : 'combobox';
    if (tag === 'input') {
      if (['button', 'submit', 'reset', 'image'].includes(type)) return 'button';
      if (type === 'checkbox') return 'checkbox';
      if (type === 'radio') return 'radio';
      if (type === 'range') return 'slider';
      if (type === 'number') return 'spinbutton';
      if (type === 'search') return el.hasAttribute('list') ? 'combobox' : 'searchbox';
      if (['', 'text', 'email', 'tel', 'url'].includes(type)) return el.hasAttribute('list') ? 'combobox' : 'textbox';
      return null;  // hidden, password, file, color, date ... have no ARIA role
    }
    return null;
  }
  const roleOf = el => {
    const explicit = norm(el.getAttribute('role')).split(' ')[0];
    return explicit || implicitRole(el);
  };

  // ---- text of a subtree, with img alt text, skipping hidden parts
  function textOf(node) {
    let out = '';
    for (const child of node.childNodes) {
      if (child.nodeType === Node.TEXT_NODE) out += child.textContent;
      else if (child.nodeType === Node.ELEMENT_NODE) {
        const st = getComputedStyle(child);
        if (st.display === 'none' || st.visibility === 'hidden' || child.hidden) continue;
        if (child.tagName === 'IMG') out += ' ' + (child.getAttribute('alt') || '') + ' ';
        else out += ' ' + textOf(child) + ' ';
      }
    }
    return out;
  }

  // ---- <label> text: explicit (for=) and wrapping labels, in DOM order
  const labelText = el => {
    if (!el.labels || el.labels.length === 0) return null;
    return orNull(norm(Array.from(el.labels).map(l => textOf(l)).join(' ')));
  };

  // ---- accessible name (simplified accname: labelledby, aria-label, label, content, title/placeholder)
  function accessibleName(el, role, label) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    const ids = norm(el.getAttribute('aria-labelledby'));
    if (ids) {
      const root = el.getRootNode();
      const text = norm(ids.split(' ').map(id => {
        const ref = root.getElementById ? root.getElementById(id) : document.getElementById(id);
        return ref ? textOf(ref) : '';
      }).join(' '));
      if (text) return text;
    }
    const aria = norm(el.getAttribute('aria-label'));
    if (aria) return aria;
    if (tag === 'input' && ['submit', 'reset', 'button'].includes(type)) {
      if (el.hasAttribute('value')) return orNull(norm(el.getAttribute('value')));
      if (type === 'submit') return 'Submit';
      if (type === 'reset') return 'Reset';
    }
    if (tag === 'input' && type === 'image') return orNull(norm(el.getAttribute('alt'))) || 'Submit';
    if (label) return label;
    const nameFromContent = ['button', 'link', 'checkbox', 'radio', 'tab', 'menuitem', 'menuitemcheckbox',
                             'menuitemradio', 'switch', 'option'].includes(role)
                            && !['input', 'select', 'textarea'].includes(tag);
    if (nameFromContent) {
      const text = norm(textOf(el));
      if (text) return text;
    }
    return orNull(norm(el.getAttribute('title'))) || orNull(norm(el.getAttribute('placeholder')));
  }

  // ---- visibility
  function visibilityOf(el, rect) {
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (el.tagName === 'INPUT' && type === 'hidden') return 'hidden';
    if (el.closest('[hidden]')) return 'hidden';
    const st = getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden' || st.visibility === 'collapse') return 'hidden';
    for (let n = el; n; n = parentOf(n)) {
      if (parseFloat(getComputedStyle(n).opacity) === 0) return 'hidden';
    }
    if (rect.width === 0 || rect.height === 0) return 'hidden';
    if (rect.right + window.scrollX <= 0 || rect.bottom + window.scrollY <= 0) return 'hidden';
    for (let n = el; n; n = parentOf(n)) {
      if (n.inert) return 'inaccessible';
    }
    const cx = rect.left + rect.width / 2, cy = rect.top + rect.height / 2;
    if (cx >= 0 && cy >= 0 && cx < window.innerWidth && cy < window.innerHeight) {
      const hit = el.getRootNode().elementFromPoint ? el.getRootNode().elementFromPoint(cx, cy)
                                                    : document.elementFromPoint(cx, cy);
      const ownLabel = hit && el.labels && Array.from(el.labels).some(l => l === hit || l.contains(hit));
      if (hit && hit !== el && !el.contains(hit) && !hit.contains(el) && !ownLabel) return 'inaccessible';
    }
    return 'visible';
  }

  // ---- container in one format
  function containerOf(el) {
    const form = el.form || el.closest('form');
    if (form) {
      if (form.id) return `form#${form.id}`;
      if (form.getAttribute('name')) return `form[name=${form.getAttribute('name')}]`;
      return 'form';
    }
    for (let n = parentOf(el); n; n = parentOf(n)) {
      const tag = n.tagName.toLowerCase();
      const role = norm(n.getAttribute('role')).split(' ')[0];
      if (LANDMARK_ROLES.includes(role)) return n.id ? `${tag}#${n.id}` : `${tag}[role=${role}]`;
      if (LANDMARK_TAGS.includes(tag)) {
        if (tag === 'section' && !n.hasAttribute('aria-label') && !n.hasAttribute('aria-labelledby')) continue;
        return n.id ? `${tag}#${n.id}` : tag;
      }
    }
    return null;
  }

  function attributesOf(el) {
    const out = {};
    for (const attr of el.attributes) {
      if (keptAttributes.includes(attr.name) || attr.name.startsWith('aria-')) out[attr.name] = attr.value;
    }
    return out;
  }

  window.scrollTo(0, 0);
  const results = [];
  let errors = 0;
  for (const el of elements) {
    try {
      const tag = el.tagName.toLowerCase();
      const rect = el.getBoundingClientRect();
      const role = roleOf(el);
      const label = labelText(el);
      const isField = ['input', 'select', 'textarea'].includes(tag);
      let snippet = el.outerHTML;
      if (tag === 'input' && (el.getAttribute('type') || '').toLowerCase() === 'password' && el.hasAttribute('value')) {
        const copy = el.cloneNode(false);  // never copy a password value into the snippet
        copy.setAttribute('value', '[redacted]');
        snippet = copy.outerHTML;
      }
      if (snippet.length > snippetMax) snippet = snippet.slice(0, snippetMax) + '…';
      results.push({
        tag,
        type: orNull(el.getAttribute('type')),
        role: orNull(role),
        accessible_name: orNull(accessibleName(el, role, label)),
        label,
        visible_text: isField ? null : orNull(norm(el.innerText || '').slice(0, 200)),
        attributes: attributesOf(el),
        visibility: visibilityOf(el, rect),
        bbox: (rect.width > 0 && rect.height > 0)
          ? {x: rect.left + window.scrollX, y: rect.top + window.scrollY, width: rect.width, height: rect.height}
          : null,
        container: containerOf(el),
        href: tag === 'a' ? el.getAttribute('href') : null,
        dom_snippet: snippet,
      });
    } catch (e) {
      errors += 1;
    }
  }
  return {elements: results, errors, frames};
}
"""


def run_extraction(page: Any) -> dict:
    """Evaluate the extraction script; returns {"elements": [...], "errors": n, "frames": n}."""
    return page.evaluate(
        EXTRACT_JS, {"roles": INTERACTIVE_ROLES, "keptAttributes": KEPT_ATTRIBUTES, "snippetMax": SNIPPET_MAX}
    )


def _round_bbox(raw: dict | None) -> BBox | None:
    if raw is None:
        return None
    return BBox(**{k: round(float(v), 1) for k, v in raw.items()})


def to_finding(index: int, raw: dict) -> Finding:
    """Turn one raw element (from EXTRACT_JS) into a Finding without locators."""
    attributes = raw["attributes"]
    fingerprint = Fingerprint(
        role=raw["role"],
        accessible_name=raw["accessible_name"],
        tag=raw["tag"],
        type=raw["type"],
        container=raw["container"],
        id=attributes.get("id"),
        name=attributes.get("name"),
        data_testid=attributes.get("data-testid"),
        label=raw["label"],
    )
    return Finding(
        finding_id=f"f_{index:03d}",
        tag=raw["tag"],
        type=raw["type"],
        role=raw["role"],
        accessible_name=raw["accessible_name"],
        label=raw["label"],
        visible_text=raw["visible_text"],
        attributes=attributes,
        visibility=Visibility(raw["visibility"]),
        bbox=_round_bbox(raw["bbox"]),
        container=raw["container"],
        fingerprint=fingerprint,
        dom_snippet=raw["dom_snippet"],
    )


def extract_findings(page: Any) -> tuple[list[Finding], list[dict], dict]:
    """Return (findings, raw elements, stats) for the page. Raw elements carry extra hints (href)."""
    raw = run_extraction(page)
    findings = [to_finding(i, el) for i, el in enumerate(raw["elements"], start=1)]
    return findings, raw["elements"], {"errors": raw["errors"], "frames": raw["frames"]}
