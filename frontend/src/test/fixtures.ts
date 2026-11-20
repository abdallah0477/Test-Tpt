// Typed access to the fixture Inspection (shaped per contracts.Inspection).
import type { Finding, Inspection, InspectionStatus } from '../api/types'
import raw from './inspection.fixture.json'

// JSON imports are typed loosely (e.g. `status: string`), so go through `unknown` once, here.
export const fixtureInspection = raw as unknown as Inspection
export const fixtureFindings: Finding[] = fixtureInspection.findings ?? []

export function inspectionWithStatus(status: InspectionStatus, reason: string | null = null): Inspection {
  return { ...fixtureInspection, status, reason }
}

/** The fixture Findings plus a search box outside the login form (for filter tests). */
export const loginAndSearchFindings: Finding[] = [
  ...fixtureFindings,
  {
    ...fixtureFindings[0],
    finding_id: 'f_004',
    type: 'search',
    role: 'searchbox',
    accessible_name: 'Search',
    label: 'Search',
    attributes: { type: 'search', name: 'q' },
    container: 'form#search',
    locators: [],
  },
]

/** `count` copies of the first Finding with ids f_001..., for palette tests. */
export function manyFindings(count: number): Finding[] {
  return Array.from({ length: count }, (_, i) => ({
    ...fixtureFindings[0],
    finding_id: `f_${String(i + 1).padStart(3, '0')}`,
    accessible_name: `Field ${i + 1}`,
    bbox: { x: 10, y: 40 * i, width: 100, height: 30 },
  }))
}
