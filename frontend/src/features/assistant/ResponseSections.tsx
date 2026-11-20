import type { FindingRef, ResponseItem, ResponseSections as Sections } from '../../api/types'
import { SECTION_TITLES } from './assistantText'
import { findingName } from '../inspection/findingText'
import { resolveRef, splitFindingIds, useFindingLinks } from './findingLinks'

/** A Finding mention: a link-styled button when it resolves, plain text otherwise. */
export function FindingLink({ findingRef, label }: { findingRef: FindingRef; label?: string }) {
  const ctx = useFindingLinks()
  const resolved = resolveRef(ctx, findingRef)
  if (!resolved.finding) return <span className="finding-ref-plain">{label ?? findingRef.finding_id}</span>
  const text = label ?? `#${resolved.number} ${findingName(resolved.finding)}`
  return (
    <button
      type="button"
      className="finding-link"
      onClick={() => ctx.openFinding(findingRef.finding_id)}
      aria-label={`Open finding ${resolved.number}: ${findingName(resolved.finding)}`}
    >
      {text}
    </button>
  )
}

function ItemText({ item, inspectionId }: { item: ResponseItem; inspectionId: string | null }) {
  // Inline ids (e.g. "f_003") become links when they are among the item's refs.
  const refIds = new Set((item.refs ?? []).map((r) => r.finding_id))
  return (
    <>
      {splitFindingIds(item.text).map((part, index) =>
        refIds.has(part) && inspectionId ? (
          <FindingLink key={index} findingRef={{ inspection_id: inspectionId, finding_id: part }} label={part} />
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  )
}

/** Observed / Inferred meaning / Unverified / Next step; empty sections are omitted (FR-15). */
export function ResponseSectionsView({ sections }: { sections: Sections | undefined }) {
  const { inspectionId } = useFindingLinks()
  const shown = SECTION_TITLES.filter(([key]) => (sections?.[key] ?? []).length > 0)
  if (shown.length === 0) return <p className="muted">The assistant returned no statements.</p>
  return (
    <>
      {shown.map(([key, title]) => (
        <section key={key} className={`response-section section-${key}`}>
          <h4>{title}</h4>
          <ul>
            {(sections?.[key] ?? []).map((item, index) => (
              <li key={index}>
                <ItemText item={item} inspectionId={inspectionId} />
                {(item.refs ?? []).length > 0 && (
                  <span className="item-refs">
                    {' '}
                    (
                    {(item.refs ?? []).map((ref, i) => (
                      <span key={`${ref.finding_id}-${i}`}>
                        {i > 0 && ', '}
                        <FindingLink findingRef={ref} />
                      </span>
                    ))}
                    )
                  </span>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </>
  )
}
