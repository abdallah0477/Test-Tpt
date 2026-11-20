// Resolving FindingRefs in assistant output to Findings of the shown Inspection.
// A ref that doesn't resolve is shown as plain text (never a dangling link) and logged.
import { createContext, useContext } from 'react'
import type { Finding, FindingRef } from '../../api/types'

export interface FindingLinkContext {
  inspectionId: string | null
  findings: Finding[]
  /** Opens the Finding in the detail panel and highlights it in the table and screenshot. */
  openFinding: (findingId: string) => void
}

export const FindingLinks = createContext<FindingLinkContext>({ inspectionId: null, findings: [], openFinding: () => {} })

export function useFindingLinks(): FindingLinkContext {
  return useContext(FindingLinks)
}

export interface ResolvedRef {
  ref: FindingRef
  finding: Finding | null
  number: number | null
}

const warned = new Set<string>()

export function resolveRef(ctx: FindingLinkContext, ref: FindingRef): ResolvedRef {
  if (ref.inspection_id === ctx.inspectionId) {
    const index = ctx.findings.findIndex((f) => f.finding_id === ref.finding_id)
    if (index >= 0) return { ref, finding: ctx.findings[index], number: index + 1 }
  }
  const key = `${ref.inspection_id}/${ref.finding_id}`
  if (!warned.has(key)) {
    warned.add(key)
    console.warn('assistant output names a Finding that is not in the shown Inspection; shown as plain text', ref)
  }
  return { ref, finding: null, number: null }
}

/** Splits text on inline finding ids such as "f_003" so they can be linked too. */
export function splitFindingIds(text: string): string[] {
  return text.split(/(\bf_\d{3,}\b)/)
}
