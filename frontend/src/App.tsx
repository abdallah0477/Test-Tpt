import { errorMessage } from './api/client'
import { useInspection } from './api/inspection'
import { InspectionWorkspace } from './features/inspection/InspectionWorkspace'
import { JobProgress } from './features/inspection/JobProgress'
import { UrlBar } from './features/inspection/UrlBar'
import { useInspectionFlow } from './features/inspection/useInspectionFlow'
import { InspectionHistory } from './features/session/InspectionHistory'
import { useSessionEditing } from './features/session/useSessionEditing'
import { UsagePanel } from './features/usage/UsagePanel'
import { BrowserView } from './shell/BrowserView'
import { HealthIndicator } from './shell/HealthIndicator'

export default function App() {
  const flow = useInspectionFlow()
  const inspection = useInspection(flow.shownId)
  const editing = useSessionEditing(flow.sessionId)

  const history = (
    <>
      <InspectionHistory sessionId={flow.sessionId} activeId={flow.shownId} onOpen={flow.open} />
      <UsagePanel sessionId={flow.sessionId} />
    </>
  )

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">Web Testing Assistant</h1>
        <UrlBar busy={flow.busy} onStart={flow.start} serverError={flow.startError} />
        <HealthIndicator />
      </header>

      <BrowserView />

      {flow.job && (
        <div className="job-area">
          <JobProgress job={flow.jobEvents} />
          {flow.jobEvents.failure && (
            <section className="banner banner-unreachable" role="alert">
              <h2 className="banner-title">
                <span aria-hidden="true">✕</span> Inspection job failed
              </h2>
              <p>
                {flow.jobEvents.failure.message} ({flow.jobEvents.failure.code})
              </p>
              <div className="banner-actions">
                <button type="button" className="btn" onClick={() => flow.retry(flow.job!.inspection_id)}>
                  Retry
                </button>
              </div>
            </section>
          )}
          {flow.jobEvents.state === 'closed' && (
            <button type="button" className="btn" onClick={() => flow.open(flow.job!.inspection_id)}>
              Open result of {flow.job.inspection_id}
            </button>
          )}
        </div>
      )}
      {flow.actionError && (
        <p className="field-error job-area" role="alert">
          {flow.actionError}
        </p>
      )}

      <div className="workspace">
        {inspection.data ? (
          <InspectionWorkspace
            key={inspection.data.inspection_id}
            inspection={inspection.data}
            busy={flow.busy}
            onRetry={() => flow.retry(inspection.data.inspection_id)}
            onReinspect={flow.reinspect}
            editing={editing}
            side={history}
          />
        ) : (
          <>
            <section className="area-main" aria-label="Inspection results">
              {flow.shownId && inspection.isPending ? (
                <p className="empty-note">Loading inspection {flow.shownId}…</p>
              ) : inspection.isError ? (
                <p className="field-error" role="alert">
                  Could not load inspection {flow.shownId}: {errorMessage(inspection.error)}
                </p>
              ) : (
                <p className="empty-note">
                  {flow.job
                    ? 'The inspection is running; results appear here when it finishes.'
                    : 'Enter a page URL above and click “Start inspection”. The page opens in the live browser and its interactive elements are listed here.'}
                </p>
              )}
            </section>
            <aside className="area-side" aria-label="Details">
              {history}
            </aside>
          </>
        )}
      </div>
    </div>
  )
}
