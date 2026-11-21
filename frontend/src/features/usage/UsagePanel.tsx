import { errorMessage } from '../../api/client'
import { usageExportUrl, useSessionUsage } from '../../api/usage'
import { Icon } from '../../shell/Icon'
import { formatSeconds, formatTokens, plural } from './usageFormat'

/** Session model usage totals and the "Export usage" download (Story 3.5). */
export function UsagePanel({ sessionId }: { sessionId: string | null }) {
  const usage = useSessionUsage(sessionId)
  return (
    <section className="usage-panel" aria-labelledby="usage-title">
      <h2 id="usage-title" className="section-title">
        Model usage
      </h2>
      {sessionId === null ? (
        <p className="muted">No session yet.</p>
      ) : usage.isPending ? (
        <p className="muted">Loading...</p>
      ) : usage.isError ? (
        <p className="field-error">Could not load usage: {errorMessage(usage.error)}</p>
      ) : (
        <>
          <dl className="usage-stats" aria-label={`${plural(usage.data.total_calls, 'model call')}, ${plural(usage.data.responses.length, 'response')}`}>
            <div>
              <dt>Model calls</dt>
              <dd>{usage.data.total_calls}</dd>
            </div>
            <div>
              <dt>Tokens</dt>
              <dd>{formatTokens(usage.data.total_tokens)}</dd>
            </div>
            <div>
              <dt>Model time</dt>
              <dd>{formatSeconds(usage.data.total_response_ms)}</dd>
            </div>
            <div>
              <dt>Responses</dt>
              <dd>{usage.data.responses.length}</dd>
            </div>
          </dl>
          <a className="btn btn-small" href={usageExportUrl(sessionId)} download>
            <Icon name="download" /> Export usage
          </a>
        </>
      )}
    </section>
  )
}
