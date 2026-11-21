import { errorMessage } from '../../api/client'
import { useSessionInspections } from '../../api/session'

interface InspectionHistoryProps {
  sessionId: string | null
  activeId: string | null
  onOpen: (inspectionId: string) => void
}

/** Earlier Inspections of this session; each one stays stored and can be reopened (Story 1.11). */
export function InspectionHistory({ sessionId, activeId, onOpen }: InspectionHistoryProps) {
  const history = useSessionInspections(sessionId)

  return (
    <section className="history" aria-labelledby="history-title">
      <h2 id="history-title" className="section-title">
        Inspection history
      </h2>
      {sessionId === null ? (
        <p className="muted">No session yet. Start an inspection to create one.</p>
      ) : history.isPending ? (
        <p className="muted">Loading...</p>
      ) : history.isError ? (
        <p className="field-error">Could not load history: {errorMessage(history.error)}</p>
      ) : history.data.length === 0 ? (
        <p className="muted">No inspections in this session yet.</p>
      ) : (
        <ol className="history-list" reversed>
          {[...history.data].reverse().map((item) => (
            <li key={item.inspection_id}>
              <button
                type="button"
                className="history-item"
                aria-current={item.inspection_id === activeId ? 'true' : undefined}
                onClick={() => onOpen(item.inspection_id)}
              >
                <span className="history-url">{item.requested_url}</span>
                <span className="history-meta">
                  <span className={`badge st-${item.status}`}>{item.status.replace('_', ' ')}</span>
                  <span>{item.counts.total} elements</span>
                  <span>{new Date(item.captured_at).toLocaleTimeString()}</span>
                  {item.inspection_id === activeId && <span className="history-shown">Shown</span>}
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
