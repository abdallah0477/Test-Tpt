import { useState } from 'react'
import type { LocatorCandidate } from '../../api/types'
import { rankLocators, uniquenessLabel } from './findingText'

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false // clipboard API missing (non-secure context) or permission denied
  }
}

export function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')
  async function onClick() {
    setState((await copyText(text)) ? 'copied' : 'failed')
    setTimeout(() => setState('idle'), 1500)
  }
  return (
    <button type="button" className="btn btn-small" onClick={onClick} aria-label={`Copy ${label}`}>
      {state === 'copied' ? 'Copied' : state === 'failed' ? 'Copy failed' : 'Copy'}
    </button>
  )
}

function LocatorRow({ locator, best }: { locator: LocatorCandidate; best?: boolean }) {
  const uniqueness = uniquenessLabel(locator)
  return (
    <li className={`locator${best ? ' locator-best' : ''}${uniqueness.unique ? '' : ' locator-not-unique'}`}>
      <code className="locator-expr">{locator.expr}</code>
      <div className="locator-meta">
        <span className="badge">{locator.strategy}</span>
        <span className={`badge rel-${locator.reliability}`}>Reliability: {locator.reliability}</span>
        <span className={`badge ${uniqueness.unique ? 'match-unique' : 'match-warn'}`}>
          {uniqueness.unique ? '' : '⚠ '}
          {uniqueness.text}
        </span>
        <CopyButton text={locator.expr} label={`locator ${locator.expr}`} />
      </div>
    </li>
  )
}

/** Locator candidates: best one prominent, alternatives behind a disclosure (Story 1.9). */
export function LocatorList({ locators }: { locators: LocatorCandidate[] }) {
  if (locators.length === 0) return <p className="muted">No locator candidates were generated.</p>
  const [best, ...alternatives] = rankLocators(locators)
  return (
    <div className="locators">
      <h4>Best locator</h4>
      <ul className="locator-list">
        <LocatorRow locator={best} best />
      </ul>
      {alternatives.length > 0 && (
        <details>
          <summary>Alternatives ({alternatives.length})</summary>
          <ul className="locator-list">
            {alternatives.map((locator) => (
              <LocatorRow key={`${locator.rank}-${locator.expr}`} locator={locator} />
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
