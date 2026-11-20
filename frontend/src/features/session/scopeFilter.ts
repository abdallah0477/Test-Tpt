// Group filters over recorded Findings (Story 2.3, FR-12).
// This MIRRORS backend/app/utils/scope_filter.py so the UI can show a live count without
// a round-trip. Keep both in sync:
// - All active criteria combine with AND. An empty list / null criterion does not filter.
// - container:      Finding.container === value (exact string, e.g. "form#login").
// - element_types:  Finding.tag or Finding.type is in the list (case-insensitive).
// - include_hidden: false keeps only visibility "visible" (drops hidden and inaccessible).
// - only_clickable: keeps Findings a user can click that are not disabled.
// - roles:          Finding.role is in the list (case-insensitive).
// - exclude_types:  drops Findings whose tag or type is in the list.
// - exclude_roles:  drops Findings whose role is in the list.
// The result is a subset of the given Findings in their original order: filters never add anything.
import type { Finding, ScopeFilters } from '../../api/types'

/** Any subset of the filter fields; missing fields mean "don't filter". */
export type FilterInput = Partial<ScopeFilters>

export const CLICKABLE_TAGS = new Set(['button', 'a', 'summary', 'select', 'option'])
export const CLICKABLE_INPUT_TYPES = new Set(['button', 'submit', 'reset', 'checkbox', 'radio', 'image', 'file'])
export const CLICKABLE_ROLES = new Set(['button', 'link', 'checkbox', 'radio', 'menuitem', 'tab', 'switch', 'option', 'combobox'])

/** Filters with every field filled in; the defaults are the "no filtering" values. */
export type FullFilters = Required<ScopeFilters>

export const NO_FILTERS: FullFilters = {
  container: null,
  element_types: [],
  include_hidden: true,
  only_clickable: false,
  roles: [],
  exclude_types: [],
  exclude_roles: [],
}

export function withDefaults(filters: FilterInput | null | undefined): FullFilters {
  return { ...NO_FILTERS, ...(filters ?? {}) }
}

/** True when at least one criterion would narrow the Findings. */
export function hasActiveFilters(filters: FilterInput): boolean {
  const f = withDefaults(filters)
  return (
    !!f.container?.trim() ||
    lower(f.element_types).size > 0 ||
    !f.include_hidden ||
    f.only_clickable ||
    lower(f.roles).size > 0 ||
    lower(f.exclude_types).size > 0 ||
    lower(f.exclude_roles).size > 0
  )
}

function lower(values: string[]): Set<string> {
  return new Set(values.map((v) => v.trim().toLowerCase()).filter((v) => v !== ''))
}

/** The "kinds" of a Finding: its tag and its type, lower-cased. */
function kinds(finding: Finding): Set<string> {
  return new Set([finding.tag, finding.type].filter((k): k is string => !!k).map((k) => k.toLowerCase()))
}

function intersects(a: Set<string>, b: Set<string>): boolean {
  for (const value of a) if (b.has(value)) return true
  return false
}

export function isClickable(finding: Finding): boolean {
  const attrs = finding.attributes ?? {}
  if ('disabled' in attrs || attrs['aria-disabled'] === 'true') return false
  const tag = finding.tag.toLowerCase()
  const role = (finding.role ?? '').toLowerCase()
  if (tag === 'input') return CLICKABLE_INPUT_TYPES.has((finding.type || 'text').toLowerCase())
  return CLICKABLE_TAGS.has(tag) || CLICKABLE_ROLES.has(role)
}

export function matchesFilters(finding: Finding, filters: FilterInput): boolean {
  const f = withDefaults(filters)
  const container = f.container?.trim()
  if (container && finding.container !== container) return false
  const types = lower(f.element_types)
  if (types.size > 0 && !intersects(kinds(finding), types)) return false
  if (!f.include_hidden && finding.visibility !== 'visible') return false
  if (f.only_clickable && !isClickable(finding)) return false
  const roles = lower(f.roles)
  if (roles.size > 0 && !roles.has((finding.role ?? '').toLowerCase())) return false
  if (intersects(kinds(finding), lower(f.exclude_types))) return false
  if (finding.role && lower(f.exclude_roles).has(finding.role.toLowerCase())) return false
  return true
}

export function applyFilters(findings: Finding[], filters: FilterInput): Finding[] {
  return findings.filter((finding) => matchesFilters(finding, filters))
}

/** Values actually observed in this Inspection, for the filter dropdowns (never invented). */
export function observedOptions(findings: Finding[]) {
  const sorted = (values: Iterable<string>) => [...new Set(values)].sort((a, b) => a.localeCompare(b))
  return {
    containers: sorted(findings.map((f) => f.container).filter((v): v is string => !!v)),
    kinds: sorted(findings.flatMap((f) => [...kinds(f)])),
    roles: sorted(findings.map((f) => f.role?.toLowerCase()).filter((v): v is string => !!v)),
  }
}
