import { useState, type FormEvent } from 'react'
import type { ClarificationTurn } from '../../api/types'
import { openTurn } from './assistantText'
import { FindingLink } from './ResponseSections'

interface ClarificationPanelProps {
  turns: ClarificationTurn[]
  busy: boolean
  onAnswer: (turn: ClarificationTurn, text: string) => void
  onSkip: (turn: ClarificationTurn) => void
}

/** The clarification conversation: the open question with Answer / Skip, and earlier turns. Skip is explicit only. */
export function ClarificationPanel({ turns, busy, onAnswer, onSkip }: ClarificationPanelProps) {
  const open = openTurn(turns)
  const closed = turns.filter((t) => t !== open)
  const [answer, setAnswer] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!open || answer.trim() === '') return
    onAnswer(open, answer.trim())
    setAnswer('')
  }

  if (turns.length === 0) return null
  return (
    <section className="clarification" aria-labelledby="clarification-title">
      <h3 id="clarification-title">Clarification</h3>
      {closed.length > 0 && (
        <ol className="clarification-history">
          {closed.map((turn) => (
            <li key={turn.clr_id}>
              <p className="clr-question">
                <span className="badge assistant-tag">Assistant</span> {turn.question}
              </p>
              <p className="clr-answer">
                <span className="badge">You</span> {turn.skipped ? <em>Skipped</em> : turn.answer}
              </p>
            </li>
          ))}
        </ol>
      )}
      {open && (
        <form className="clarification-open" onSubmit={submit}>
          <p className="clr-question">
            <span className="badge assistant-tag">Assistant asks</span> {open.question}
            {(open.refs ?? []).map((ref) => (
              <span key={ref.finding_id}>
                {' '}
                <FindingLink findingRef={ref} />
              </span>
            ))}
          </p>
          <label htmlFor={`answer-${open.clr_id}`}>Your answer</label>
          <textarea id={`answer-${open.clr_id}`} rows={2} value={answer} onChange={(e) => setAnswer(e.target.value)} />
          <div className="goal-actions">
            <button type="submit" className="btn btn-primary" disabled={busy || answer.trim() === ''}>
              Answer
            </button>
            <button type="button" className="btn" disabled={busy} onClick={() => onSkip(open)}>
              Skip
            </button>
          </div>
        </form>
      )}
    </section>
  )
}
