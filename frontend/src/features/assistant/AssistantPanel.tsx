import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { startClarify, startSuggestions, startSummary } from '../../api/assistant'
import { errorCode } from '../../api/client'
import { answerClarification, confidenceQuery, skipClarification, storeClarification, useConfidence } from '../../api/session'
import type { AssistantResponse, ClarificationTurn } from '../../api/types'
import type { SessionEditing } from '../session/useSessionEditing'
import { AssistantProgress } from './AssistantProgress'
import { ClarificationPanel } from './ClarificationPanel'
import { ConfidenceMeter } from './ConfidenceMeter'
import { ResponseCard } from './ResponseCard'
import { assistantError, useAssistantJob } from './useAssistantJob'

/**
 * Scope summary and clarification conversation (Stories 3.3, 3.4).
 * Summarize -> (clarification question -> answer -> confidence re-check)* -> summary.
 * Skip -> suggestions from the Scope only.
 */
export function AssistantPanel({ editing }: { editing: SessionEditing }) {
  const queryClient = useQueryClient()
  const session = editing.session
  const sessionId = session?.session_id ?? null
  const confidence = useConfidence(sessionId, session?.rev)
  const [shown, setShown] = useState<string[]>([]) // response ids, newest first
  const [note, setNote] = useState<string | null>(null)

  const job = useAssistantJob(sessionId, async (response: AssistantResponse) => {
    setShown((ids) => [response.response_id, ...ids.filter((id) => id !== response.response_id)])
    if (response.mode !== 'clarification') return
    if ((response.sections?.next_step ?? []).length === 0) {
      setNote('The assistant could not phrase a grounded question. You can edit the goal or Summarize again.')
      return
    }
    try {
      await editing.writeAsync((s) => storeClarification(s.session_id, s.rev ?? 0, response.response_id))
    } catch (e) {
      const code = errorCode(e)
      if (code === 'duplicate_question') setNote('The assistant repeated an earlier question. Answer differently, Skip, or edit the goal.')
      else if (code !== 'rev_conflict') setNote(assistantError(e)) // rev_conflict is reported by the editing hook
    }
  })

  const busy = job.running || editing.saving

  async function answer(turn: ClarificationTurn, text: string) {
    setNote(null)
    try {
      const stored = await editing.writeAsync((s) => answerClarification(s.session_id, s.rev ?? 0, turn.clr_id, text))
      const report = await queryClient.fetchQuery(confidenceQuery(stored.session_id, stored.rev ?? 0))
      // Re-check confidence: proceed to the summary once actionable, otherwise ask the next question.
      await job.start(() => (report.actionable ? startSummary : startClarify)(stored.session_id))
    } catch (e) {
      if (errorCode(e) !== 'rev_conflict') setNote(assistantError(e))
    }
  }

  async function skip(turn: ClarificationTurn) {
    setNote(null)
    try {
      const stored = await editing.writeAsync((s) => skipClarification(s.session_id, s.rev ?? 0, turn.clr_id))
      await job.start(() => startSuggestions(stored.session_id))
    } catch (e) {
      if (errorCode(e) !== 'rev_conflict') setNote(assistantError(e))
    }
  }

  return (
    <section className="assistant-panel" aria-labelledby="assistant-panel-title">
      <div className="assistant-panel-head">
        <h2 id="assistant-panel-title" className="section-title">
          Assistant
        </h2>
        <button
          type="button"
          className="btn btn-primary"
          disabled={!sessionId || busy}
          onClick={() => sessionId && job.start(() => startSummary(sessionId))}
        >
          Summarize Scope
        </button>
      </div>
      <ConfidenceMeter report={confidence.data} />
      <AssistantProgress job={job.events} />
      {(job.error || note) && (
        <p className="field-error" role="alert">
          {job.error ?? note}
        </p>
      )}
      <ClarificationPanel turns={session?.clarification ?? []} busy={busy} onAnswer={answer} onSkip={skip} />
      {sessionId && shown.map((id) => <ResponseCard key={id} responseId={id} sessionId={sessionId} />)}
    </section>
  )
}
