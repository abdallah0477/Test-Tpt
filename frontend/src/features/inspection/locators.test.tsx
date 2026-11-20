import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { fixtureFindings } from '../../test/fixtures'
import { observedValidationRules } from './findingText'
import { LocatorList } from './LocatorList'

afterEach(cleanup)

const email = fixtureFindings[0]

describe('locator candidates', () => {
  it('shows the rank-1 locator as best and flags non-unique alternatives', () => {
    const { container } = render(<LocatorList locators={email.locators ?? []} />)
    const best = container.querySelector('.locator-best')!
    expect(best.querySelector('.locator-expr')!.textContent).toBe('page.get_by_label("Email")')
    expect(best.textContent).toContain('Unique (1 match)')
    expect(best.textContent).toContain('Reliability: High')

    const alternative = container.querySelector('details .locator')!
    expect(alternative.classList.contains('locator-not-unique')).toBe(true)
    expect(alternative.textContent).toContain('Not unique (2 matches)')
    expect(screen.getByText('Alternatives (1)')).toBeTruthy()
  })

  it('has a copy button for every locator', () => {
    const { container } = render(<LocatorList locators={email.locators ?? []} />)
    for (const item of Array.from(container.querySelectorAll<HTMLElement>('.locator'))) {
      expect(within(item).getByRole('button', { name: /^Copy locator/ })).toBeTruthy()
    }
  })
})

describe('observed validation rules', () => {
  it('lists only attributes that are present', () => {
    expect(observedValidationRules(email).map((r) => r.attribute)).toEqual(['required', 'type', 'maxlength'])
    expect(observedValidationRules(fixtureFindings[1])).toEqual([]) // submit button
  })
})
