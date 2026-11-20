import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, beforeAll, describe, expect, it } from 'vitest'
import { fixtureFindings } from '../../test/fixtures'
import { FindingsTable } from './FindingsTable'
import { ScreenshotView } from './ScreenshotView'

// jsdom does not decode images, so give the screenshot a natural size of 1000x800.
beforeAll(() => {
  Object.defineProperty(HTMLImageElement.prototype, 'naturalWidth', { configurable: true, get: () => 1000 })
  Object.defineProperty(HTMLImageElement.prototype, 'naturalHeight', { configurable: true, get: () => 800 })
})
afterEach(cleanup)

function Linked() {
  const [activeId, setActiveId] = useState<string | null>(null)
  return (
    <>
      <ScreenshotView src="/shot.png" findings={fixtureFindings} activeId={activeId} onSelect={setActiveId} />
      <FindingsTable findings={fixtureFindings} activeId={activeId} onSelect={setActiveId} />
    </>
  )
}

function renderLinked() {
  const view = render(<Linked />)
  fireEvent.load(screen.getByAltText(/full-page screenshot/i))
  const markers = Array.from(view.container.querySelectorAll<HTMLButtonElement>('.marker'))
  const rows = within(screen.getByRole('table')).getAllByRole('row').slice(1) // skip header
  return { markers, rows }
}

describe('screenshot markers and Findings table', () => {
  it('numbers markers and rows one-to-one', () => {
    const { markers, rows } = renderLinked()
    expect(rows.map((row) => row.dataset.number)).toEqual(['1', '2', '3'])
    // f_003 has no bbox, so only two markers; their numbers match the rows of the same Findings.
    expect(markers.map((m) => m.dataset.number)).toEqual(['1', '2'])
    expect(markers[0].getAttribute('aria-label')).toBe('Finding 1: Email')
    expect(within(rows[0]).getByRole('button').textContent).toBe('Email')
    expect(markers[1].getAttribute('aria-label')).toBe('Finding 2: Sign in')
    expect(within(rows[1]).getByRole('button').textContent).toBe('Sign in')
  })

  it('places markers from bbox, scaled to the image size', () => {
    const { markers } = renderLinked()
    // bbox {x:100, y:50, w:200, h:30} on a 1000x800 image
    expect(markers[0].style.left).toBe('10%')
    expect(markers[0].style.top).toBe('6.25%')
    expect(markers[0].style.width).toBe('20%')
  })

  it('shows status from visibility', () => {
    const { rows } = renderLinked()
    expect(rows.map((row) => (row as HTMLTableRowElement).cells[3].textContent)).toEqual(['Detected', 'Detected', 'Hidden'])
  })

  it('selecting a row highlights its marker', () => {
    const { rows } = renderLinked()
    fireEvent.click(within(rows[1]).getByRole('button'))
    const markers = Array.from(document.querySelectorAll<HTMLButtonElement>('.marker'))
    expect(markers[1].getAttribute('aria-pressed')).toBe('true')
    expect(markers[1].classList.contains('marker-active')).toBe(true)
    expect(markers[0].getAttribute('aria-pressed')).toBe('false')
  })
})

describe('screenshot zoom and badges', () => {
  it('defaults to 100% and switches to Fit / 150%', () => {
    const { container } = render(<Linked />)
    fireEvent.load(screen.getByAltText(/full-page screenshot/i))
    const frame = container.querySelector<HTMLElement>('.screenshot-frame')!
    expect(frame.style.width).toBe('1000px')
    expect(screen.getByRole('button', { name: '100%' }).getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(screen.getByRole('button', { name: '150%' }))
    expect(frame.style.width).toBe('1500px')
    fireEvent.click(screen.getByRole('button', { name: 'Fit' }))
    expect(frame.style.width).toBe('100%')
  })

  it('puts the badge inside the box only at the page edge', () => {
    const { markers } = renderLinked()
    // both fixture boxes start at x=100, y>=50: badge outside
    expect(markers.some((m) => m.classList.contains('marker-badge-inside'))).toBe(false)
  })
})
