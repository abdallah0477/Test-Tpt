import type { CSSProperties } from 'react'
import type { Finding } from '../../api/types'
import type { ScopeColorAssignment } from '../session/scopeColors'
import { findingName, findingType, numberFindings, VISIBILITY_LABEL } from './findingText'

interface FindingsTableProps {
  findings: Finding[]
  /** Finding shown in the detail panel (clicking a name). */
  activeId: string | null
  onSelect: (findingId: string) => void
  /** Scope colours by finding id; a Finding is in Scope when it has a colour. */
  scopeColors?: Map<string, ScopeColorAssignment>
  /** Called by the Scope checkbox. Omit to hide the Scope column. */
  onToggleScope?: (findingId: string) => void
  scopeDisabled?: boolean
}

/** "input[type=email] (textbox)" with line-break opportunities before "[" and " (". */
function TypeText({ text }: { text: string }) {
  const parts = text.split(/(?=\[|\s\()/)
  return (
    <code>
      {parts.map((part, index) => (
        <span key={index}>
          {index > 0 && <wbr />}
          {part}
        </span>
      ))}
    </code>
  )
}

/**
 * Findings table; row numbers are the same numbers as the screenshot markers (Story 1.8).
 * Two separate actions per row: the "Scope" checkbox toggles the Finding in/out of the Scope
 * (Story 2.2), and the name button opens the Finding in the detail panel.
 */
export function FindingsTable({ findings, activeId, onSelect, scopeColors, onToggleScope, scopeDisabled }: FindingsTableProps) {
  if (findings.length === 0) return <p className="empty-note">No Findings were captured.</p>
  return (
    <table className="findings-table">
      <caption className="section-title">Findings ({findings.length})</caption>
      <thead>
        <tr>
          {onToggleScope && (
            <th scope="col" className="col-scope">
              Scope
            </th>
          )}
          <th scope="col" className="col-number">
            #
          </th>
          <th scope="col">Name</th>
          <th scope="col" className="col-type">
            Type
          </th>
          <th scope="col" className="col-status">
            Status
          </th>
        </tr>
      </thead>
      <tbody>
        {numberFindings(findings).map(({ number, finding }) => {
          const active = finding.finding_id === activeId
          const color = scopeColors?.get(finding.finding_id)
          const classes = [active ? 'row-active' : '', color ? 'row-scoped' : ''].filter(Boolean).join(' ')
          const style = color ? ({ '--scope-color': color.color } as CSSProperties) : undefined
          return (
            <tr key={finding.finding_id} className={classes || undefined} style={style} data-number={number}>
              {onToggleScope && (
                <td className="scope-cell col-scope">
                  <input
                    type="checkbox"
                    checked={!!color}
                    disabled={scopeDisabled}
                    onChange={() => onToggleScope(finding.finding_id)}
                    aria-label={`Finding ${number} in Scope`}
                  />
                </td>
              )}
              <td className="col-number">
                {color ? (
                  <span className="scope-swatch" style={{ background: color.color, color: color.text }}>
                    {number}
                  </span>
                ) : (
                  number
                )}
              </td>
              <td>
                {/* The name is a button so rows can be opened in the detail panel with the keyboard. */}
                <button type="button" className="row-select" aria-pressed={active} onClick={() => onSelect(finding.finding_id)}>
                  {findingName(finding)}
                </button>
                {!finding.bbox && <span className="muted"> (no marker: no position)</span>}
              </td>
              <td className="col-type">
                <TypeText text={findingType(finding)} />
              </td>
              <td className="col-status">
                <span className={`badge vis-${finding.visibility}`}>{VISIBILITY_LABEL[finding.visibility]}</span>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
