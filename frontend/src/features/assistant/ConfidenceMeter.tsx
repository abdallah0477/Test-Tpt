import type { ConfidenceReport } from '../../api/types'
import { confidenceText } from './assistantText'

/** Score vs threshold as a meter plus text (never colour alone), with the signals it came from. */
export function ConfidenceMeter({ report }: { report: ConfidenceReport | undefined }) {
  if (!report) return <p className="muted">Confidence: not computed yet.</p>
  const s = report.signals
  const signal = (ok: boolean, text: string) => (
    <li>
      <span aria-hidden="true">{ok ? '✓' : '✕'}</span> {text}: {ok ? 'yes' : 'no'}
    </li>
  )
  return (
    <div className={`confidence ${report.actionable ? 'confidence-ok' : 'confidence-low'}`}>
      <p className="confidence-text">{confidenceText(report)}</p>
      <meter min={0} max={1} low={report.threshold} optimum={1} value={report.score} aria-label="Confidence">
        {Math.round(report.score * 100)}%
      </meter>
      <details>
        <summary>Why?</summary>
        <ul className="confidence-signals">
          {signal(s.has_goal, 'A goal is set')}
          {signal(s.references, 'The goal refers to observed elements or areas')}
          {signal(s.scope_non_empty, 'The Scope is not empty')}
          {signal(s.names_action, 'The goal names an action')}
          <li>Open ambiguities: {s.open_ambiguities}</li>
          {(report.unmatched_mentions ?? []).length > 0 && (
            <li>Not observed on the page: {(report.unmatched_mentions ?? []).map((m) => `“${m}”`).join(', ')}</li>
          )}
        </ul>
      </details>
    </div>
  )
}
