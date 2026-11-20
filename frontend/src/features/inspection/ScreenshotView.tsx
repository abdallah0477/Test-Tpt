import { useEffect, useRef, useState, type CSSProperties } from 'react'
import type { Finding } from '../../api/types'
import type { ScopeColorAssignment } from '../session/scopeColors'
import { findingName, numberFindings } from './findingText'

interface ScreenshotViewProps {
  src: string | null
  findings: Finding[]
  activeId: string | null
  onSelect: (findingId: string) => void
  /** Findings in Scope get their Scope colour as outline; others keep the grey dashed style. */
  scopeColors?: Map<string, ScopeColorAssignment>
}

type Zoom = 'fit' | 1 | 1.5
const ZOOMS: { value: Zoom; label: string }[] = [
  { value: 'fit', label: 'Fit' },
  { value: 1, label: '100%' },
  { value: 1.5, label: '150%' },
]

/** Badges sit outside the box's top-left corner, unless the box touches the page's left/top edge. */
const BADGE_ROOM = 18

/**
 * Full-page screenshot with a numbered marker on each Finding's bbox (Story 1.8).
 * bbox is in page pixels; markers are placed in percent of the image's natural size,
 * so they stay aligned at any zoom. Default zoom is 100% (scroll inside the panel),
 * so small elements stay readable and markers don't pile up.
 */
export function ScreenshotView({ src, findings, activeId, onSelect, scopeColors }: ScreenshotViewProps) {
  const [natural, setNatural] = useState<{ width: number; height: number } | null>(null)
  const [zoom, setZoom] = useState<Zoom>(1)
  const panelRef = useRef<HTMLDivElement | null>(null)
  const activeRef = useRef<HTMLButtonElement | null>(null)

  useEffect(() => {
    // Scroll only the screenshot panel (not the page) so the active marker is centred.
    const panel = panelRef.current
    const marker = activeRef.current
    if (!panel || !marker) return
    const visible =
      marker.offsetLeft >= panel.scrollLeft &&
      marker.offsetTop >= panel.scrollTop &&
      marker.offsetLeft + marker.offsetWidth <= panel.scrollLeft + panel.clientWidth &&
      marker.offsetTop + marker.offsetHeight <= panel.scrollTop + panel.clientHeight
    if (visible) return // already in view: don't move the screenshot around
    panel.scrollTo?.({
      left: marker.offsetLeft + marker.offsetWidth / 2 - panel.clientWidth / 2,
      top: marker.offsetTop + marker.offsetHeight / 2 - panel.clientHeight / 2,
      behavior: 'smooth',
    })
  }, [activeId, natural, zoom])

  if (!src) return <p className="empty-note">No screenshot was captured for this inspection.</p>

  const frameWidth = zoom === 'fit' || !natural ? '100%' : `${natural.width * zoom}px`

  return (
    <div className="screenshot">
      <div className="zoom-bar" role="group" aria-label="Screenshot zoom">
        {ZOOMS.map(({ value, label }) => (
          <button
            key={label}
            type="button"
            className="btn btn-small"
            aria-pressed={zoom === value}
            onClick={() => setZoom(value)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="screenshot-scroll" ref={panelRef} aria-label="Page screenshot">
        <div className="screenshot-frame" style={{ width: frameWidth }}>
          <img
            src={src}
            alt="Full-page screenshot of the inspected page"
            onLoad={(event) =>
              setNatural({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })
            }
          />
          {natural &&
            natural.width > 0 &&
            numberFindings(findings).map(({ number, finding }) => {
              if (!finding.bbox) return null
              const { x, y, width, height } = finding.bbox
              const active = finding.finding_id === activeId
              const color = scopeColors?.get(finding.finding_id)
              const inside = x < BADGE_ROOM || y < BADGE_ROOM
              const classes = [
                'marker',
                active ? 'marker-active' : '',
                color ? 'marker-scoped' : '',
                inside ? 'marker-badge-inside' : '',
              ]
                .filter(Boolean)
                .join(' ')
              return (
                <button
                  key={finding.finding_id}
                  type="button"
                  ref={active ? activeRef : undefined}
                  className={classes}
                  data-number={number}
                  aria-label={`Finding ${number}: ${findingName(finding)}${color ? ' (in Scope)' : ''}`}
                  aria-pressed={active}
                  style={{
                    ...(color ? ({ '--scope-color': color.color, '--scope-text': color.text } as CSSProperties) : {}),
                    left: `${(x / natural.width) * 100}%`,
                    top: `${(y / natural.height) * 100}%`,
                    width: `${(width / natural.width) * 100}%`,
                    height: `${(height / natural.height) * 100}%`,
                  }}
                  onClick={() => onSelect(finding.finding_id)}
                >
                  <span className="marker-number">{number}</span>
                </button>
              )
            })}
        </div>
      </div>
    </div>
  )
}
