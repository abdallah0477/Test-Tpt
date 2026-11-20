import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { fixtureFindings, manyFindings } from '../../test/fixtures'
import { FindingsTable } from '../inspection/FindingsTable'
import { ScreenshotView } from '../inspection/ScreenshotView'
import { assignScopeColors, SCOPE_PALETTE } from './scopeColors'
import { onlyRecorded, toggleId } from './scopeOps'

beforeAll(() => {
  Object.defineProperty(HTMLImageElement.prototype, 'naturalWidth', { configurable: true, get: () => 1000 })
  Object.defineProperty(HTMLImageElement.prototype, 'naturalHeight', { configurable: true, get: () => 1000 })
})
afterEach(cleanup)

describe('Scope colours', () => {
  it('gives every selected Finding a distinct colour up to the palette size', () => {
    expect(SCOPE_PALETTE.length).toBeGreaterThanOrEqual(8)
    const ids = manyFindings(SCOPE_PALETTE.length).map((f) => f.finding_id)
    const colors = [...assignScopeColors(ids).values()]
    expect(new Set(colors.map((c) => c.color)).size).toBe(ids.length)
    expect(colors.some((c) => c.reused)).toBe(false)
  })

  it('reuses colours beyond the palette and flags them', () => {
    const ids = manyFindings(SCOPE_PALETTE.length + 2).map((f) => f.finding_id)
    const colors = assignScopeColors(ids)
    const first = colors.get(ids[0])!
    const wrapped = colors.get(ids[SCOPE_PALETTE.length])!
    expect(wrapped.color).toBe(first.color)
    expect(wrapped.reused && first.reused).toBe(true)
    expect(colors.get(ids[5])!.reused).toBe(false)
  })

  it('always shows the Finding number on the outline, also beyond the palette', () => {
    const findings = manyFindings(SCOPE_PALETTE.length + 2)
    const colors = assignScopeColors(findings.map((f) => f.finding_id))
    const { container } = render(<ScreenshotView src="/s.png" findings={findings} activeId={null} onSelect={() => {}} scopeColors={colors} />)
    fireEvent.load(screen.getByRole('img'))
    const last = container.querySelector<HTMLElement>(`.marker[data-number="${findings.length}"]`)!
    expect(last.classList.contains('marker-scoped')).toBe(true)
    expect(last.textContent).toBe(String(findings.length))
    expect(last.style.getPropertyValue('--scope-color')).toBe(SCOPE_PALETTE[1].color)
  })

  it('unselected markers have no Scope colour', () => {
    const colors = assignScopeColors(['f_002'])
    const { container } = render(<ScreenshotView src="/s.png" findings={fixtureFindings} activeId={null} onSelect={() => {}} scopeColors={colors} />)
    fireEvent.load(screen.getByRole('img'))
    const [one, two] = Array.from(container.querySelectorAll<HTMLElement>('.marker'))
    expect(one.classList.contains('marker-scoped')).toBe(false)
    expect(one.style.getPropertyValue('--scope-color')).toBe('')
    expect(two.classList.contains('marker-scoped')).toBe(true)
  })
})

describe('toggling Findings in and out of Scope', () => {
  it('toggleId adds then removes', () => {
    const once = toggleId([], 'f_002')
    expect(once).toEqual(['f_002'])
    expect(toggleId(once, 'f_001')).toEqual(['f_002', 'f_001'])
    expect(toggleId(['f_002', 'f_001'], 'f_002')).toEqual(['f_001'])
  })

  it('onlyRecorded drops ids that were never observed', () => {
    expect(onlyRecorded(['f_001', 'f_999'], fixtureFindings)).toEqual(['f_001'])
  })

  it('the Scope checkbox toggles, separately from opening details', () => {
    const onToggle = vi.fn()
    const onSelect = vi.fn()
    render(
      <FindingsTable
        findings={fixtureFindings}
        activeId={null}
        onSelect={onSelect}
        scopeColors={assignScopeColors(['f_002'])}
        onToggleScope={onToggle}
      />,
    )
    const box1 = screen.getByRole('checkbox', { name: 'Finding 1 in Scope' }) as HTMLInputElement
    const box2 = screen.getByRole('checkbox', { name: 'Finding 2 in Scope' }) as HTMLInputElement
    expect([box1.checked, box2.checked]).toEqual([false, true])
    fireEvent.click(box1)
    expect(onToggle).toHaveBeenCalledWith('f_001')
    expect(onSelect).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Email' }))
    expect(onSelect).toHaveBeenCalledWith('f_001')
    expect(onToggle).toHaveBeenCalledOnce()
  })
})
