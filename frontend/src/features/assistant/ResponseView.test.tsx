import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AssistantResponse } from '../../api/types'
import { fixtureFindings } from '../../test/fixtures'
import { confidenceText } from './assistantText'
import { ConfidenceMeter } from './ConfidenceMeter'
import { FindingLinks } from './findingLinks'
import { ResponseView } from './ResponseCard'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

const ref = (finding_id: string, inspection_id = 'ins_fixture01') => ({ inspection_id, finding_id })

function response(extra: Partial<AssistantResponse> = {}): AssistantResponse {
  return {
    response_id: 'resp_1',
    session_id: 'ses_1',
    inspection_id: 'ins_fixture01',
    feature: 'assistant',
    mode: 'summary',
    sections: {
      observed: [{ text: 'The email field f_001 is required.', refs: [ref('f_001')] }],
      inferred: [],
      unverified: [{ text: 'Mentions a missing element.', refs: [ref('f_999')] }],
      next_step: [{ text: 'Try submitting an empty form.', refs: [] }],
    },
    validation: { outcome: 'passed', retries: 1, errors: [], blocked_count: 0 },
    ...extra,
  }
}

function renderView(r: AssistantResponse) {
  const openFinding = vi.fn()
  render(
    <FindingLinks.Provider value={{ inspectionId: 'ins_fixture01', findings: fixtureFindings, openFinding }}>
      <ResponseView response={r} />
    </FindingLinks.Provider>,
  )
  return openFinding
}

describe('ResponseView', () => {
  it('shows non-empty sections in order and omits empty ones', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    renderView(response())
    const titles = screen.getAllByRole('heading', { level: 4 }).map((h) => h.textContent)
    expect(titles).toEqual(['Observed', 'Unverified', 'Next step'])
    expect(screen.getByText('Assistant output')).toBeTruthy()
    expect(screen.getByText('Validated after 1 retry')).toBeTruthy()
  })

  it('Finding mentions open the detail panel; unresolved refs are plain text and logged', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    // (unresolved refs are logged once per ref, so use one no other test uses)
    const r = response()
    r.sections!.unverified = [{ text: 'Mentions a missing element.', refs: [ref('f_998')] }]
    const openFinding = renderView(r)
    // One link for the inline id "f_001" in the text, one in the refs list.
    const links = screen.getAllByRole('button', { name: 'Open finding 1: Email' })
    expect(links.map((l) => l.textContent)).toEqual(['f_001', '#1 Email'])
    for (const link of links) fireEvent.click(link)
    expect(openFinding).toHaveBeenCalledTimes(2)
    expect(openFinding).toHaveBeenCalledWith('f_001')
    expect(screen.queryByRole('button', { name: /f_998/ })).toBeNull()
    expect(screen.getByText('f_998')).toBeTruthy()
    expect(warn).toHaveBeenCalled()
  })

  it('shows the withheld notice and blocked outcome', () => {
    renderView(
      response({
        withheld_notice: '2 claims could not be verified and were withheld.',
        validation: { outcome: 'blocked', retries: 2, errors: [], blocked_count: 2 },
        sections: { observed: [], inferred: [], unverified: [], next_step: [] },
      }),
    )
    expect(screen.getByRole('note').textContent).toContain('2 claims could not be verified')
    expect(screen.getByText(/Blocked after 2 retries: 2 claims withheld/)).toBeTruthy()
    expect(screen.getByText('The assistant returned no statements.')).toBeTruthy()
  })
})

describe('ConfidenceMeter', () => {
  const report = {
    score: 0.35,
    actionable: false,
    threshold: 0.6,
    signals: { has_goal: true, references: false, scope_non_empty: true, names_action: true, open_ambiguities: 1 },
    unmatched_mentions: ['search bar'],
  }

  it('states score, threshold and verdict in text', () => {
    expect(confidenceText(report)).toBe('Confidence 35% (threshold 60%): needs clarification')
    expect(confidenceText({ ...report, score: 0.8, actionable: true })).toBe('Confidence 80% (threshold 60%): goal is actionable')
  })

  it('renders a meter plus the signals', () => {
    render(<ConfidenceMeter report={report} />)
    expect(screen.getByRole('meter', { name: 'Confidence' })).toBeTruthy()
    expect(screen.getByText(/needs clarification/)).toBeTruthy()
    expect(screen.getByText(/“search bar”/)).toBeTruthy()
  })
})
