import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { InspectionStatus } from '../../api/types'
import { inspectionWithStatus } from '../../test/fixtures'
import { StatusBanner } from './StatusBanner'

afterEach(cleanup)

function renderBanner(status: InspectionStatus, reason: string | null = null) {
  const onRetry = vi.fn()
  const onReinspect = vi.fn()
  const view = render(
    <StatusBanner inspection={inspectionWithStatus(status, reason)} busy={false} onRetry={onRetry} onReinspect={onReinspect} />,
  )
  return { ...view, onRetry, onReinspect }
}

describe('StatusBanner', () => {
  it.each([
    ['complete', 'Inspection complete'],
    ['partial', 'Partial inspection'],
    ['unreachable', 'Page unreachable'],
    ['timeout', 'Page load timed out'],
    ['login_required', 'Login required'],
  ] as const)('%s has its own title', (status, title) => {
    renderBanner(status)
    expect(screen.getByRole('heading').textContent).toContain(title)
  })

  it('offers Retry on every non-complete status, not on complete', () => {
    for (const status of ['partial', 'unreachable', 'timeout', 'login_required'] as const) {
      const { onRetry, unmount } = renderBanner(status)
      fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
      expect(onRetry).toHaveBeenCalledOnce()
      unmount()
    }
    renderBanner('complete')
    expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull()
  })

  it('unreachable shows the reason and possible causes', () => {
    renderBanner('unreachable', 'net::ERR_NAME_NOT_RESOLVED')
    expect(screen.getByText(/ERR_NAME_NOT_RESOLVED/)).toBeTruthy()
    expect(screen.getByText(/DNS/)).toBeTruthy()
    expect(screen.getByText(/refused/)).toBeTruthy()
  })

  it('login_required tells the tester to sign in by hand and offers Re-inspect', () => {
    const { onReinspect } = renderBanner('login_required')
    expect(screen.getByText(/sign in by hand/i)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Re-inspect' }))
    expect(onReinspect).toHaveBeenCalledOnce()
  })

  it('partial shows inspected vs inaccessible counts and the reason', () => {
    const inspection = inspectionWithStatus('partial', 'cross-origin iframe')
    inspection.counts = { total: 5, visible: 3, hidden: 0, inaccessible: 2 }
    render(<StatusBanner inspection={inspection} busy={false} onRetry={vi.fn()} onReinspect={vi.fn()} />)
    expect(screen.getByText(/3 of 5 elements were inspected; 2/)).toBeTruthy()
    expect(screen.getByText(/cross-origin iframe/)).toBeTruthy()
  })
})
