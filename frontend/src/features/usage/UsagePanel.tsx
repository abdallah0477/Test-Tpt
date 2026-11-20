import { errorMessage } from '../../api/client'
import { usageExportUrl, useSessionUsage } from '../../api/usage'
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
        <p className="muted">Loading…</p>
      ) : usage.isError ? (
        <p className="field-error">Could not load usage: {errorMessage(usage.error)}</p>
      ) : (
        <>
          <p>
            {plural(usage.data.total_calls, 'model call')} · {formatTokens(usage.data.total_tokens)} tokens ·{' '}
            {formatSeconds(usage.data.total_response_ms)} model time · {plural(usage.data.responses.length, 'response')}
          </p>
          <a className="btn" href={usageExportUrl(sessionId)} download>
            Export usage
          </a>
        </>
      )}
    </section>
  )
}
