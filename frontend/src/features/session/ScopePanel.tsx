import type { Finding } from '../../api/types'
import { findingName, findingType, rankLocators, VISIBILITY_LABEL } from '../inspection/findingText'
import type { ScopeColorAssignment } from './scopeColors'

interface ScopePanelProps {
  findings: Finding[]
  scopeIds: string[]
  colors: Map<string, ScopeColorAssignment>
  saving: boolean
  onRemove: (findingId: string) => void
  onClear: () => void
  onShow: (findingId: string) => void
}

/** Number swatch in the Finding's Scope colour; the number is always shown, never colour alone. */
export function ScopeSwatch({ number, color }: { number: number; color?: ScopeColorAssignment }) {
  return (
    <span
      className={`scope-swatch${color ? '' : ' scope-swatch-none'}`}
      style={color ? { background: color.color, color: color.text } : undefined}
    >
      {number}
    </span>
  )
}

/** The Findings in Scope with their key details (Story 2.2). */
export function ScopePanel({ findings, scopeIds, colors, saving, onRemove, onClear, onShow }: ScopePanelProps) {
  const numberOf = new Map(findings.map((f, index) => [f.finding_id, index + 1]))
  const byId = new Map(findings.map((f) => [f.finding_id, f]))

  return (
    <section className="scope-panel" aria-labelledby="scope-title">
      <div className="scope-head">
        <h2 id="scope-title" className="section-title">
          Scope
        </h2>
        <span className="scope-counter" role="status">
          {scopeIds.length} {scopeIds.length === 1 ? 'element' : 'elements'} selected
        </span>
        {scopeIds.length > 0 && (
          <button type="button" className="btn btn-small" onClick={onClear} disabled={saving}>
            Clear Scope
          </button>
        )}
      </div>
      {scopeIds.length === 0 ? (
        <p className="muted">Tick the “Scope” box of a Finding, or apply filters, to add elements.</p>
      ) : (
        <ul className="scope-list">
          {scopeIds.map((id) => {
            const finding = byId.get(id)
            if (!finding) return null
            const number = numberOf.get(id) ?? 0
            const best = rankLocators(finding.locators ?? [])[0]
            return (
              <li key={id} className="scope-item" style={{ borderLeftColor: colors.get(id)?.color }}>
                <ScopeSwatch number={number} color={colors.get(id)} />
                <div className="scope-item-body">
                  <button type="button" className="row-select" onClick={() => onShow(id)}>
                    {findingName(finding)}
                  </button>
                  <span className="muted">
                    <code>{findingType(finding)}</code> · {VISIBILITY_LABEL[finding.visibility]}
                    {finding.container && (
                      <>
                        {' '}
                        · in <code>{finding.container}</code>
                      </>
                    )}
                  </span>
                  {best && <code className="scope-locator">{best.expr}</code>}
                </div>
                <button
                  type="button"
                  className="btn btn-small"
                  onClick={() => onRemove(id)}
                  disabled={saving}
                  aria-label={`Remove finding ${number} from Scope`}
                >
                  Remove
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
