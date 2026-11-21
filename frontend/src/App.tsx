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
import { BrandMark, Icon } from './shell/Icon'

const STEPS = [
  {
    title: 'Inspect a page',
    text: 'Enter a URL. The page opens in an isolated browser and every interactive element is listed with verified locators.',
  },
  {
    title: 'Set a goal and a scope',
    text: 'Describe what you want to test, then select the elements that matter, by hand or with filters.',
  },
  {
    title: 'Get a grounded summary',
    text: 'A local model summarizes the scope. Every claim cites an observed element; anything it cannot back up is withheld.',
  },
]

function Welcome() {
  return (
    <section className="welcome" aria-labelledby="welcome-title">
      <div className="welcome-frame">
        <h2 id="welcome-title" className="welcome-title">
          Test-TPT
        </h2>
        <p className="welcome-lede">
          Human-in-the-loop web testing. Inspect any page, choose what to test, and get a summary that only states what
          was observed.
        </p>
      </div>
      <ol className="welcome-steps">
        {STEPS.map((step) => (
          <li key={step.title} className="welcome-step">
            <h3>{step.title}</h3>
            <p>{step.text}</p>
          </li>
        ))}
      </ol>
      <p className="welcome-hint">Start by entering a page URL in the bar above.</p>
    </section>
  )
}

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
        <div className="app-header-inner">
          <div className="app-header-top">
            <h1 className="brand">
              <BrandMark />
              <span className="brand-name">Test-TPT</span>
              <span className="brand-tag">Web testing assistant</span>
            </h1>
            <HealthIndicator />
          </div>
          <UrlBar busy={flow.busy} onStart={flow.start} serverError={flow.startError} />
        </div>
      </header>

      <main className="app-main">
        <BrowserView />

        {flow.job && (
          <div className="job-area">
            <JobProgress job={flow.jobEvents} />
            {flow.jobEvents.failure && (
              <section className="banner banner-unreachable" role="alert">
                <h2 className="banner-title">
                  <Icon name="cross" /> Inspection job failed
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
                  <p className="empty-note">Loading inspection {flow.shownId}...</p>
                ) : inspection.isError ? (
                  <p className="field-error" role="alert">
                    Could not load inspection {flow.shownId}: {errorMessage(inspection.error)}
                  </p>
                ) : (
                  flow.job ? (
                    <p className="empty-note">The inspection is running. Results appear here when it finishes.</p>
                  ) : (
                    <Welcome />
                  )
                )}
              </section>
              <aside className="area-side" aria-label="Details">
                {history}
              </aside>
            </>
          )}
        </div>
      </main>

      <footer className="app-footer">
        <span>Test-TPT</span>
        <span>Runs locally. Credentials stay in the isolated browser and are never sent to the model.</span>
      </footer>
    </div>
  )
}
