import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import type { ModelCallRecord, ResponseUsage } from '../../api/types'
import { UsageBadge } from './UsageBadge'
import { badgeText, shortModel } from './usageFormat'

afterEach(cleanup)

const usage: ResponseUsage = {
  response_id: 'resp_1',
  model: 'qwen3:4b-instruct-2507-q4_K_M',
  calls: 2,
  reused_calls: 0,
  total_tokens: 1250,
  response_ms: 6400,
  load_ms: 900,
  outcome: 'passed',
  call_ids: ['call_1', 'call_2'],
}

const record = (call_id: string, attempt: number, outcome: ModelCallRecord['validation_outcome']): ModelCallRecord => ({
  call_id,
  session_id: 'ses_1',
  feature: 'assistant',
  response_id: 'resp_1',
  attempt,
  role: 'assistant',
  provider: 'ollama',
  model: usage.model,
  setup: 'RTX 3060 6GB, Ollama 0.40.16',
  prompt_tokens: 500,
  completion_tokens: 125,
  total_tokens: 625,
  tokens_source: 'runtime',
  load_ms: 450,
  response_ms: 3200,
  started_at: '2026-11-20T10:00:00Z',
  validation_outcome: outcome,
  reused: false,
})

describe('usage badge', () => {
  it('formats "model · N calls · T tokens · X.X s"', () => {
    expect(shortModel('qwen3:4b-instruct-2507-q4_K_M')).toBe('qwen3:4b')
    expect(shortModel('qwen3:4b')).toBe('qwen3:4b')
    expect(badgeText(usage)).toBe('qwen3:4b · 2 calls · 1,250 tokens · 6.4 s')
    expect(badgeText({ ...usage, calls: 1, reused_calls: 1 })).toBe('qwen3:4b · 1 call (+1 reused) · 1,250 tokens · 6.4 s')
  })

  it('expands to one row per call with model time and load time', () => {
    const records = [record('call_1', 1, 'failed_retried'), record('call_2', 2, 'passed'), { ...record('other', 1, 'passed'), response_id: 'resp_2' }]
    const { container } = render(<UsageBadge usage={usage} records={records} />)
    const details = container.querySelector('details')!
    expect(details.open).toBe(false)
    fireEvent.click(screen.getByText(/2 calls/))
    expect(details.open).toBe(true)
    const rows = within(screen.getByRole('table')).getAllByRole('row').slice(1)
    expect(rows).toHaveLength(2)
    expect(rows[0].textContent).toContain('failed retried')
    expect(rows[1].textContent).toContain('3.2 s')
    expect(screen.getByRole('columnheader', { name: 'Model time' })).toBeTruthy()
  })
})

describe('plural', () => {
  it('pluralizes counts', async () => {
    const { plural } = await import('./usageFormat')
    expect(plural(1, 'model call')).toBe('1 model call')
    expect(plural(0, 'response')).toBe('0 responses')
    expect(plural(1250, 'token')).toBe('1,250 tokens')
  })
})
