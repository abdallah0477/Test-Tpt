// Pure Scope helpers. A Scope is bound to exactly one Inspection (AD-11).
import type { Finding, FindingRef, Session } from '../../api/types'

/** Finding ids in the Session's Scope, but only when the Scope belongs to `inspectionId`. */
export function scopeIdsFor(session: Session | undefined, inspectionId: string): string[] {
  const scope = session?.scope
  if (!scope || scope.inspection_id !== inspectionId) return []
  return (scope.refs ?? []).map((ref) => ref.finding_id)
}

/** True when the Session already has a non-empty Scope for a different Inspection. */
export function scopeBelongsElsewhere(session: Session | undefined, inspectionId: string): boolean {
  const scope = session?.scope
  return !!scope?.inspection_id && scope.inspection_id !== inspectionId && (scope.refs ?? []).length > 0
}

/** Adds the id at the end, or removes it if already selected. */
export function toggleId(ids: string[], id: string): string[] {
  return ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]
}

export function removeId(ids: string[], id: string): string[] {
  return ids.filter((x) => x !== id)
}

/** Keeps only ids of recorded Findings, so nothing unobserved can enter the Scope. */
export function onlyRecorded(ids: string[], findings: Finding[]): string[] {
  const known = new Set(findings.map((f) => f.finding_id))
  return ids.filter((id) => known.has(id))
}

export function toRefs(inspectionId: string, ids: string[]): FindingRef[] {
  return ids.map((finding_id) => ({ inspection_id: inspectionId, finding_id }))
}
