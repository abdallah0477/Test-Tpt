import type { Finding } from '../../api/types'
import { inspectionUrls } from '../../api/inspection'
import { findingName, findingType, observedValidationRules, VISIBILITY_LABEL } from './findingText'
import { FindingSuggestions } from '../assistant/FindingSuggestions'
import { LocatorList } from './LocatorList'

interface FindingDetailProps {
  inspectionId: string
  finding: Finding
  number: number
  /** Needed for assistant suggestions; null hides nothing but disables the button. */
  sessionId?: string | null
}

/** Everything observed about one Finding (Story 1.9). Observed evidence and Assistant output are kept apart. */
export function FindingDetail({ inspectionId, finding, number, sessionId = null }: FindingDetailProps) {
  const attributes = Object.entries(finding.attributes ?? {})
  const rules = observedValidationRules(finding)

  return (
    <article className="finding-detail" aria-labelledby="finding-detail-title">
      <h2 id="finding-detail-title" className="section-title">
        #{number} {findingName(finding)}
      </h2>

      <section aria-label="Observed evidence" className="observed">
        <dl className="facts">
          <dt>Type</dt>
          <dd>
            <code>{findingType(finding)}</code>
          </dd>
          <dt>Visibility</dt>
          <dd>
            <span className={`badge vis-${finding.visibility}`}>{VISIBILITY_LABEL[finding.visibility]}</span>
          </dd>
          {finding.container && (
            <>
              <dt>Container</dt>
              <dd>
                <code>{finding.container}</code>
              </dd>
            </>
          )}
        </dl>

        <h3>Screenshot crop</h3>
        {finding.crop ? (
          <img
            className="crop"
            src={inspectionUrls.crop(inspectionId, finding.finding_id)}
            alt={`Crop of finding ${number} with the element highlighted`}
          />
        ) : (
          <p className="muted">No crop (the element has no visible position).</p>
        )}

        <h3>DOM snippet</h3>
        {/* React escapes text content, so the HTML is shown, never rendered. */}
        {finding.dom_snippet ? (
          <pre className="dom-snippet">
            <code>{finding.dom_snippet}</code>
          </pre>
        ) : (
          <p className="muted">No DOM snippet captured.</p>
        )}

        <h3>Attributes</h3>
        {attributes.length > 0 ? (
          <table className="attr-table">
            <thead>
              <tr>
                <th scope="col">Attribute</th>
                <th scope="col">Value</th>
              </tr>
            </thead>
            <tbody>
              {attributes.map(([name, value]) => (
                <tr key={name}>
                  <td>
                    <code>{name}</code>
                  </td>
                  <td>
                    <code>{value === '' ? '(present)' : value}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">No attributes observed.</p>
        )}

        {rules.length > 0 && (
          <>
            <h3>Validation rules (observed)</h3>
            <ul className="rules">
              {rules.map((rule) => (
                <li key={rule.attribute}>
                  <code>
                    {rule.attribute}
                    {rule.value !== '' && `="${rule.value}"`}
                  </code>{' '}
                  {rule.meaning}
                </li>
              ))}
            </ul>
          </>
        )}

        <h3>Locator candidates</h3>
        <LocatorList locators={finding.locators ?? []} />
      </section>

      <section className="assistant-area" aria-labelledby="assistant-title">
        <h3 id="assistant-title">Assistant</h3>
        <p className="muted">Assistant output, kept separate from the observed evidence above.</p>
        <FindingSuggestions
          key={finding.finding_id}
          sessionId={sessionId}
          findingRef={{ inspection_id: inspectionId, finding_id: finding.finding_id }}
        />
      </section>
    </article>
  )
}
