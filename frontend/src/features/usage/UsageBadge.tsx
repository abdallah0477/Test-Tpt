import type { ModelCallRecord, ResponseUsage } from '../../api/types'
import { badgeText, formatSeconds, formatTokens } from './usageFormat'

interface UsageBadgeProps {
  usage: ResponseUsage | undefined
  /** All records of the Session; the badge picks its own by call_id. */
  records: ModelCallRecord[]
}

/** Badge "model · N calls · T tokens · X.X s"; expands to one row per model call. */
export function UsageBadge({ usage, records }: UsageBadgeProps) {
  if (!usage) return <p className="muted usage-badge-missing">Usage not recorded yet.</p>
  const ids = new Set(usage.call_ids)
  const calls = records.filter((r) => ids.has(r.call_id))
  return (
    <details className="usage-badge">
      <summary title={usage.model}>
        <span className="badge">Model usage</span> {badgeText(usage)}
      </summary>
      <p className="muted">
        Model: <code>{usage.model}</code>. Times are model time only (no browser time). Load time{' '}
        {formatSeconds(usage.load_ms)}.
      </p>
      <table className="usage-table">
        <thead>
          <tr>
            <th scope="col">Attempt</th>
            <th scope="col">Tokens (prompt + completion)</th>
            <th scope="col">Model time</th>
            <th scope="col">Load time</th>
            <th scope="col">Outcome</th>
            <th scope="col">Reused</th>
          </tr>
        </thead>
        <tbody>
          {calls.map((call) => (
            <tr key={call.call_id}>
              <td>{call.attempt}</td>
              <td>
                {formatTokens(call.total_tokens)} ({formatTokens(call.prompt_tokens)} + {formatTokens(call.completion_tokens)})
                {call.tokens_source === 'estimate' && <span className="muted"> estimated</span>}
              </td>
              <td>{formatSeconds(call.response_ms)}</td>
              <td>{formatSeconds(call.load_ms)}</td>
              <td>{call.validation_outcome.replace('_', ' ')}</td>
              <td>{call.reused ? 'yes' : 'no'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  )
}
