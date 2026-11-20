// Display helpers for Findings. They only re-word what was observed; nothing is inferred.
import type { Finding, LocatorCandidate, Visibility } from '../../api/types'

/** Visibility shown as the Findings table status (FR-3). */
export const VISIBILITY_LABEL: Record<Visibility, string> = {
  visible: 'Detected',
  hidden: 'Hidden',
  inaccessible: 'Inaccessible',
}

/** The most human name we observed for the element. */
export function findingName(finding: Finding): string {
  return (
    finding.accessible_name ||
    finding.label ||
    finding.visible_text ||
    finding.attributes?.placeholder ||
    finding.attributes?.name ||
    finding.attributes?.id ||
    `(unnamed ${finding.tag})`
  )
}

/** e.g. "button", "input[type=email]", "a (link)". */
export function findingType(finding: Finding): string {
  const base = finding.type ? `${finding.tag}[type=${finding.type}]` : finding.tag
  return finding.role && finding.role !== finding.tag ? `${base} (${finding.role})` : base
}

/** Finding numbers are positions in `inspection.findings`, 1-based; marker and row use the same number. */
export function numberFindings(findings: Finding[]): { number: number; finding: Finding }[] {
  return findings.map((finding, index) => ({ number: index + 1, finding }))
}

/** Locators best-first (rank 1 is best). */
export function rankLocators(locators: LocatorCandidate[]): LocatorCandidate[] {
  return [...locators].sort((a, b) => a.rank - b.rank)
}

/** A locator is only safe to use when it matches exactly one element. */
export function uniquenessLabel(locator: LocatorCandidate): { unique: boolean; text: string } {
  if (locator.match_count === 1) return { unique: true, text: 'Unique (1 match)' }
  if (locator.match_count === 0) return { unique: false, text: 'No match (0)' }
  return { unique: false, text: `Not unique (${locator.match_count} matches)` }
}

export interface ObservedRule {
  attribute: string
  value: string
  meaning: string
}

const VALIDATING_INPUT_TYPES = new Set(['email', 'url', 'number', 'tel', 'date', 'time', 'datetime-local', 'month', 'week'])

/** Validation rules, listed only when the attribute is actually present on the element. */
export function observedValidationRules(finding: Finding): ObservedRule[] {
  const attrs = finding.attributes ?? {}
  const rules: ObservedRule[] = []
  if ('required' in attrs) rules.push({ attribute: 'required', value: attrs.required, meaning: 'A value is required' })
  if (attrs.type && VALIDATING_INPUT_TYPES.has(attrs.type)) {
    rules.push({ attribute: 'type', value: attrs.type, meaning: `Browser checks the value is a valid ${attrs.type}` })
  }
  if ('pattern' in attrs) rules.push({ attribute: 'pattern', value: attrs.pattern, meaning: 'Value must match this pattern' })
  if ('minlength' in attrs) rules.push({ attribute: 'minlength', value: attrs.minlength, meaning: 'Minimum length' })
  if ('maxlength' in attrs) rules.push({ attribute: 'maxlength', value: attrs.maxlength, meaning: 'Maximum length' })
  if ('min' in attrs) rules.push({ attribute: 'min', value: attrs.min, meaning: 'Minimum value' })
  if ('max' in attrs) rules.push({ attribute: 'max', value: attrs.max, meaning: 'Maximum value' })
  if ('step' in attrs) rules.push({ attribute: 'step', value: attrs.step, meaning: 'Allowed step' })
  return rules
}
