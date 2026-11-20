import { describe, expect, it } from 'vitest'
import { loginAndSearchFindings as findings } from '../../test/fixtures'
import { applyFilters, hasActiveFilters, isClickable, NO_FILTERS, observedOptions } from './scopeFilter'
import { removeId } from './scopeOps'

const ids = (filters: Parameters<typeof applyFilters>[1]) => applyFilters(findings, filters).map((f) => f.finding_id)

describe('group filters (mirror of backend scope_filter.py)', () => {
  it('no filters keeps everything', () => {
    expect(ids(NO_FILTERS)).toEqual(['f_001', 'f_002', 'f_003', 'f_004'])
    expect(hasActiveFilters(NO_FILTERS)).toBe(false)
  })

  it('combines with AND: login form + inputs gives only the inputs in that form', () => {
    expect(ids({ element_types: ['input'] })).toEqual(['f_001', 'f_004']) // every input on the page
    expect(ids({ container: 'form#login' })).toEqual(['f_001', 'f_002'])
    expect(ids({ container: 'form#login', element_types: ['input'] })).toEqual(['f_001'])
  })

  it('element type matches tag or type, case-insensitively', () => {
    expect(ids({ element_types: ['EMAIL'] })).toEqual(['f_001'])
  })

  it('include_hidden=false drops hidden and inaccessible Findings', () => {
    expect(ids({ include_hidden: false })).toEqual(['f_001', 'f_002', 'f_004'])
  })

  it('only_clickable keeps buttons and links, not text inputs', () => {
    expect(ids({ only_clickable: true })).toEqual(['f_002', 'f_003'])
    expect(isClickable({ ...findings[1], attributes: { disabled: '' } })).toBe(false)
  })

  it('roles and exclusions', () => {
    expect(ids({ roles: ['button'] })).toEqual(['f_002'])
    expect(ids({ exclude_roles: ['link'] })).toEqual(['f_001', 'f_002', 'f_004'])
    expect(ids({ exclude_types: ['a', 'button'] })).toEqual(['f_001', 'f_004'])
  })

  it('never adds anything: the result is a subset in the original order', () => {
    const result = applyFilters(findings, { container: 'form#nope' })
    expect(result).toEqual([])
    const all = applyFilters(findings, { roles: ['textbox', 'button'] })
    expect(all.every((f) => findings.includes(f))).toBe(true)
  })

  it('removing one Finding after applying a filter keeps the rest', () => {
    const scope = ids({ container: 'form#login' })
    expect(removeId(scope, 'f_002')).toEqual(['f_001'])
  })

  it('offers only observed values in the dropdowns', () => {
    const options = observedOptions(findings)
    expect(options.containers).toEqual(['form#login', 'form#search'])
    expect(options.roles).toEqual(['button', 'link', 'searchbox', 'textbox'])
    expect(options.kinds).toContain('input')
  })
})
