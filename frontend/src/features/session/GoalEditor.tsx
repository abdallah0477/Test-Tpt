import { useState, type FormEvent } from 'react'
import type { GoalEntry } from '../../api/types'

interface GoalEditorProps {
  goals: GoalEntry[]
  saving: boolean
  disabled?: boolean
  onSave: (text: string) => void
}

/** Testing goal, always visible next to the Findings, with the goal history (Story 2.1). */
export function GoalEditor({ goals, saving, disabled, onSave }: GoalEditorProps) {
  const current = goals.length > 0 ? goals[goals.length - 1] : null
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')

  function startEditing() {
    setDraft(current?.text ?? '')
    setEditing(true)
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    const text = draft.trim()
    if (text === '' || text === current?.text) return
    onSave(text)
    setEditing(false)
  }

  return (
    <section className="goal" aria-labelledby="goal-title">
      <h2 id="goal-title" className="section-title">
        Testing goal
      </h2>
      {editing ? (
        <form onSubmit={submit} className="goal-form">
          <label htmlFor="goal-text" className="visually-hidden">
            Testing goal
          </label>
          <textarea
            id="goal-text"
            rows={2}
            value={draft}
            maxLength={2000}
            placeholder="e.g. Check that the login form rejects an invalid email"
            onChange={(event) => setDraft(event.target.value)}
          />
          <div className="goal-actions">
            <button type="submit" className="btn btn-primary" disabled={saving || draft.trim() === ''}>
              Save goal
            </button>
            <button type="button" className="btn" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <div className="goal-current">
          <p className={current ? 'goal-text' : 'muted'}>{current ? current.text : 'No goal yet.'}</p>
          <button type="button" className="btn btn-small" onClick={startEditing} disabled={disabled || saving}>
            {current ? 'Edit goal' : 'Set goal'}
          </button>
        </div>
      )}
      {goals.length > 1 && (
        <details className="goal-history">
          <summary>Goal history ({goals.length - 1} earlier)</summary>
          <ol reversed>
            {goals
              .slice(0, -1)
              .reverse()
              .map((goal, index) => (
                <li key={`${goal.set_at}-${index}`}>
                  {goal.text}{' '}
                  {goal.set_at && <span className="muted">({new Date(goal.set_at).toLocaleString()})</span>}
                </li>
              ))}
          </ol>
        </details>
      )}
    </section>
  )
}
