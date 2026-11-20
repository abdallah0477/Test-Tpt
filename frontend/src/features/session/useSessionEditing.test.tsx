import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Session } from '../../api/types'
import { NO_FILTERS } from './scopeFilter'
import { CONFLICT_MESSAGE, useSessionEditing } from './useSessionEditing'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const baseSession = (rev: number): Session => ({
  session_id: 'ses_1',
  rev,
  created_at: '2026-11-20T10:00:00Z',
  updated_at: '2026-11-20T10:00:00Z',
  inspection_ids: ['ins_1'],
  goals: [],
  scope: { inspection_id: null, refs: [] },
  clarification: [],
  actionable: false,
})

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

function Harness() {
  const editing = useSessionEditing('ses_1')
  return (
    <div>
      <p data-testid="rev">{editing.session?.rev ?? 'none'}</p>
      <p data-testid="message">{editing.message ?? ''}</p>
      <button onClick={() => editing.saveGoal('Test the login form')}>goal</button>
      <button onClick={() => editing.applyFilters('ins_1', { ...NO_FILTERS, container: 'form#login' }, ['f_001', 'f_002'])}>apply</button>
    </div>
  )
}

function renderHarness() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  )
}

describe('useSessionEditing', () => {
  it('on 409 rev_conflict reloads the session and asks to retry', async () => {
    let gets = 0
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'GET') return json(200, baseSession(++gets === 1 ? 1 : 2))
      return json(409, { error: { code: 'rev_conflict', message: 'stale rev', details: null } })
    })
    vi.stubGlobal('fetch', fetchMock)
    renderHarness()
    await waitFor(() => expect(screen.getByTestId('rev').textContent).toBe('1'))

    fireEvent.click(screen.getByText('goal'))
    await waitFor(() => expect(screen.getByTestId('message').textContent).toBe(CONFLICT_MESSAGE))
    await waitFor(() => expect(screen.getByTestId('rev').textContent).toBe('2')) // reloaded

    const put = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT')!
    expect(put[0]).toBe('/api/v1/session/ses_1/goal')
    expect((put[1]!.headers as Record<string, string>)['If-Match']).toBe('1')
  })

  it('apply filters stores the filters, then the Scope, each with the latest rev', async () => {
    let rev = 1
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'GET') return json(200, baseSession(rev))
      rev += 1
      return json(200, baseSession(rev))
    })
    vi.stubGlobal('fetch', fetchMock)
    renderHarness()
    await waitFor(() => expect(screen.getByTestId('rev').textContent).toBe('1'))

    fireEvent.click(screen.getByText('apply'))
    await waitFor(() => expect(screen.getByTestId('rev').textContent).toBe('3'))
    const puts = fetchMock.mock.calls.filter(([, init]) => init?.method === 'PUT')
    expect(puts.map(([url]) => url)).toEqual(['/api/v1/session/ses_1/filters', '/api/v1/session/ses_1/scope'])
    expect(puts.map(([, init]) => (init!.headers as Record<string, string>)['If-Match'])).toEqual(['1', '2'])
    expect(JSON.parse(puts[1][1]!.body as string)).toEqual({
      inspection_id: 'ins_1',
      refs: [
        { inspection_id: 'ins_1', finding_id: 'f_001' },
        { inspection_id: 'ins_1', finding_id: 'f_002' },
      ],
    })
    expect(screen.getByTestId('message').textContent).toBe('')
  })
})
