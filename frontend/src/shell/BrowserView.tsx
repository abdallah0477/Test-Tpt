import { useEffect, useState } from 'react'

// noVNC view of the Runner's visible browser. Override with VITE_NOVNC_URL in frontend/.env.local.
const NOVNC_URL: string = import.meta.env.VITE_NOVNC_URL ?? 'http://127.0.0.1:6080/vnc.html?autoconnect=1&resize=scale'
const OPEN_KEY = 'wta.browser_view_open'

// Per-viewer convenience only; storage may be unavailable, so every access is guarded.
function readOpen(): boolean {
  try {
    return window.localStorage.getItem(OPEN_KEY) === '1'
  } catch {
    return false
  }
}

function writeOpen(open: boolean) {
  try {
    window.localStorage.setItem(OPEN_KEY, open ? '1' : '0')
  } catch {
    // ignore
  }
}

type Reachability = 'checking' | 'up' | 'down'

/**
 * Collapsible live browser view (collapsed by default, state remembered per viewer).
 * The noVNC page is probed first: when it can't be reached a one-line note replaces the
 * empty black frame. Once opened, the iframe stays mounted so collapsing keeps the VNC session.
 */
export function BrowserView() {
  const [open, setOpen] = useState(readOpen)
  const [everOpened, setEverOpened] = useState(open)
  const [reach, setReach] = useState<Reachability>('checking')

  useEffect(() => {
    let cancelled = false
    // `no-cors` gives an opaque response when the server answers, and rejects when nothing listens.
    fetch(NOVNC_URL, { mode: 'no-cors' })
      .then(() => !cancelled && setReach('up'))
      .catch(() => !cancelled && setReach('down'))
    return () => {
      cancelled = true
    }
  }, [])

  function toggle() {
    const next = !open
    setOpen(next)
    writeOpen(next)
    if (next) setEverOpened(true)
  }

  return (
    <section className="browser-view" aria-labelledby="browser-view-title">
      <div className="browser-view-head">
        <h2 id="browser-view-title" className="section-title">
          Live browser
        </h2>
        <button
          type="button"
          className="btn btn-small"
          aria-expanded={open}
          aria-controls="browser-view-frame"
          onClick={toggle}
        >
          {open ? 'Collapse' : 'Expand'}
        </button>
        {reach === 'down' ? (
          <span className="muted">Live browser view is available when the Runner runs in Docker (noVNC on 127.0.0.1:6080).</span>
        ) : (
          <a className="muted" href={NOVNC_URL} target="_blank" rel="noreferrer">
            Open in new tab
          </a>
        )}
      </div>
      <div id="browser-view-frame" hidden={!open}>
        {reach === 'down' ? (
          <p className="muted">The noVNC page did not answer. Start the stack with docker compose to see the Runner's browser here.</p>
        ) : (
          everOpened && <iframe src={NOVNC_URL} title="Live Runner browser (noVNC)" className="browser-frame" />
        )}
      </div>
    </section>
  )
}
