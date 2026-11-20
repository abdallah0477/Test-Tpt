// Plain-text helpers for assistant output (kept out of component files for fast refresh).
import type { AssistantResponse, ClarificationTurn, ConfidenceReport, ResponseSections, SseEvent } from '../../api/types'

/** Pipeline step names in words; the model's raw tokens are never streamed. */
export function stepLabel(event: SseEvent): string {
  if (event.event === 'job_queued') return 'Queued'
  if (event.event === 'job_done') return 'Done'
  if (event.event === 'job_failed') return `Failed: ${event.data.error.message}`
  const { step } = event
  const { done, total } = event.data
  if (step === 'building_prompt') return 'Building prompt'
  if (step === 'calling_model') return done != null && total != null ? `Calling model (attempt ${done} of ${total})` : 'Calling model'
  if (step === 'validating') return 'Validating against the Inspection'
  const retry = /^retry_(\d+)$/.exec(step)
  if (retry) return `Retry ${retry[1]}`
  return event.data.message || step
}

export function openTurn(turns: ClarificationTurn[]): ClarificationTurn | null {
  const last = turns.length > 0 ? turns[turns.length - 1] : null
  return last && last.answer == null && !last.skipped ? last : null
}

export const MODE_LABEL: Record<AssistantResponse['mode'], string> = {
  summary: 'Scope summary',
  clarification: 'Clarification',
  suggestions: 'Suggestions (from Scope only)',
}

export function validationText(response: AssistantResponse): string {
  const { outcome, retries = 0, blocked_count = 0 } = response.validation
  const tries = `${retries} ${retries === 1 ? 'retry' : 'retries'}`
  if (outcome === 'passed') return retries === 0 ? 'Validated on the first attempt' : `Validated after ${tries}`
  if (outcome === 'failed_retried') return `Validated after ${tries}`
  return `Blocked after ${tries}: ${blocked_count} claim${blocked_count === 1 ? '' : 's'} withheld`
}

export const SECTION_TITLES: [keyof ResponseSections, string][] = [
  ['observed', 'Observed'],
  ['inferred', 'Inferred meaning'],
  ['unverified', 'Unverified'],
  ['next_step', 'Next step'],
]

export function confidenceText(report: ConfidenceReport): string {
  const pct = (value: number) => `${Math.round(value * 100)}%`
  const verdict = report.actionable ? 'goal is actionable' : 'needs clarification'
  return `Confidence ${pct(report.score)} (threshold ${pct(report.threshold)}): ${verdict}`
}
