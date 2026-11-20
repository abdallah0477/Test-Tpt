import type { Inspection, InspectionStatus } from '../../api/types'

interface StatusBannerProps {
  inspection: Inspection
  busy: boolean
  onRetry: () => void
  onReinspect: () => void
}

// Each status has its own title and symbol, so it never relies on colour alone.
const TITLES: Record<InspectionStatus, { symbol: string; title: string }> = {
  complete: { symbol: '✓', title: 'Inspection complete' },
  partial: { symbol: '◐', title: 'Partial inspection' },
  unreachable: { symbol: '✕', title: 'Page unreachable' },
  timeout: { symbol: '⏱', title: 'Page load timed out' },
  login_required: { symbol: '🔒', title: 'Login required' },
}

function Body({ inspection }: { inspection: Inspection }) {
  const { reason } = inspection
  const counts = inspection.counts ?? { total: 0, visible: 0, hidden: 0, inaccessible: 0 }
  switch (inspection.status) {
    case 'complete':
      return (
        <p>
          {counts.total === 0
            ? 'The page loaded, but no interactive elements were found.'
            : `${counts.total} elements found (${counts.visible} detected, ${counts.hidden} hidden).`}
        </p>
      )
    case 'partial':
      return (
        <>
          <p>
            {counts.total - counts.inaccessible} of {counts.total} elements were inspected; {counts.inaccessible}{' '}
            could not be inspected.
          </p>
          {reason && <p>Reason: {reason}</p>}
        </>
      )
    case 'unreachable':
      return (
        <>
          <p>The page could not be loaded, so no elements were captured.</p>
          {reason && <p>Reason: {reason}</p>}
          <p>Possible causes:</p>
          <ul>
            <li>The host name does not resolve (DNS)</li>
            <li>The server refused the connection or is not running</li>
            <li>The port or scheme is wrong (http vs https)</li>
          </ul>
        </>
      )
    case 'timeout':
      return (
        <>
          <p>The page did not finish loading within the configured timeout. Showing whatever was captured.</p>
          {reason && <p>Reason: {reason}</p>}
        </>
      )
    case 'login_required':
      return (
        <>
          <p>
            This page needs a login. Sign in by hand in the browser view below (your credentials stay in that
            browser and are never sent to the assistant), then click <strong>Re-inspect</strong>.
          </p>
          {reason && <p>Reason: {reason}</p>}
        </>
      )
  }
}

/** One banner per Inspection status (Story 1.10). Every non-complete status offers Retry. */
export function StatusBanner({ inspection, busy, onRetry, onReinspect }: StatusBannerProps) {
  const { symbol, title } = TITLES[inspection.status]
  const failed = inspection.status !== 'complete'
  return (
    <section
      className={`banner banner-${inspection.status}`}
      role={failed ? 'alert' : 'status'}
      aria-label={title}
      data-status={inspection.status}
    >
      <h2 className="banner-title">
        <span aria-hidden="true">{symbol}</span> {title}
      </h2>
      <Body inspection={inspection} />
      {failed && (
        <div className="banner-actions">
          {inspection.status === 'login_required' && (
            <button type="button" className="btn btn-primary" onClick={onReinspect} disabled={busy}>
              Re-inspect
            </button>
          )}
          <button type="button" className="btn" onClick={onRetry} disabled={busy}>
            Retry
          </button>
        </div>
      )}
    </section>
  )
}
