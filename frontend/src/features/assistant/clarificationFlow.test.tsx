import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AssistantResponse, ClarificationTurn, Session } from '../../api/types'
import { FakeEventSource, jobDone } from '../../test/fakeEventSource'
import { useSessionEditing } from '../session/useSessionEditing'
import { AssistantPanel } from './AssistantPanel'

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const QUESTION = 'Which form do you want to test: form#login or form#search?'

let session: Session
let actionable: boolean
const calls: { method: string; url: string; body: unknown }[] = []

function makeSession(clarification: ClarificationTurn[] = []): Session {
  return {
    session_id: 'ses_1',
    rev: 1,
    goals: [{ text: 'test this page', set_at: '2026-11-20T10:00:00Z' }],
    scope: { inspection_id: 'ins_1', refs: [{ inspection_id: 'ins_1', finding_id: 'f_001' }] },
    clarification,
    actionable: false,
  }
}

function responseOf(id: string, mode: AssistantResponse['mode']): AssistantResponse {
  const item = (text: string) => [{ text, refs: [] }]
  return {
    response_id: id,
    session_id: 'ses_1',
    feature: 'assistant',
    mode,
    sections: {
      observed: item(mode === 'summary' ? 'The Scope holds the email field.' : 'The page has two forms.'),
      inferred: [],
      unverified: [],
      next_step: item(mode === 'clarification' ? QUESTION : 'Try an invalid email.'),
    },
    validation: { outcome: 'passed', retries: 0, errors: [], blocked_count: 0 },
  }
}

/** Mutates the fake stored Session and bumps its rev, like v1/session. */
function write(change: (s: Session) => void) {
  change(session)
  session = { ...session, rev: (session.rev ?? 0) + 1 }
  return json(200, session)
}

async function backend(input: string, init?: RequestInit) {
  const method = init?.method ?? 'GET'
  const body = init?.body ? JSON.parse(init.body as string) : undefined
  calls.push({ method, url: input, body })
  const route = `${method} ${input.split('?')[0]}`
  const turns = () => session.clarification ?? []
  switch (route) {
    case 'GET /api/v1/session/ses_1':
      return json(200, session)
    case 'GET /api/v1/session/ses_1/confidence':
      return json(200, {
        score: actionable ? 0.8 : 0.3,
        actionable,
        threshold: 0.6,
        signals: { has_goal: true, references: actionable, scope_non_empty: true, names_action: true, open_ambiguities: 0 },
      })
    case 'GET /api/v1/usage/ses_1':
      return json(200, { session_id: 'ses_1', records: [], responses: [], total_calls: 0, total_tokens: 0, total_response_ms: 0 })
    case 'POST /api/v1/assistant/summary':
      return json(202, { job_id: actionable ? 'resp_sum' : 'resp_clr', kind: actionable ? 'summary' : 'clarification' })
    case 'POST /api/v1/assistant/clarify':
      return json(202, { job_id: 'resp_clr2', kind: 'clarification' })
    case 'POST /api/v1/assistant/suggestions':
      return json(202, { job_id: 'resp_sug', kind: 'suggestions' })
    case 'GET /api/v1/assistant/responses/resp_clr':
      return json(200, responseOf('resp_clr', 'clarification'))
    case 'GET /api/v1/assistant/responses/resp_sum':
      return json(200, responseOf('resp_sum', 'summary'))
    case 'GET /api/v1/assistant/responses/resp_sug':
      return json(200, responseOf('resp_sug', 'suggestions'))
    case 'POST /api/v1/session/ses_1/clarification':
      return write((s) => {
        s.clarification = [...turns(), { clr_id: 'clr_1', question: QUESTION, refs: [], skipped: false }]
      })
    case 'POST /api/v1/session/ses_1/clarification/clr_1/answer':
      actionable = true
      return write((s) => {
        s.clarification = turns().map((t) => ({ ...t, answer: body.text }))
      })
    case 'POST /api/v1/session/ses_1/clarification/clr_1/skip':
      return write((s) => {
        s.clarification = turns().map((t) => ({ ...t, skipped: true }))
      })
  }
  return json(404, { error: { code: 'not_found', message: route, details: null } })
}

function Harness() {
  return <AssistantPanel editing={useSessionEditing('ses_1')} />
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  )
}

async function finishJob(jobId: string) {
  await waitFor(() => expect(FakeEventSource.find(jobId)).toBeTruthy())
  act(() => FakeEventSource.find(jobId)!.emit(jobDone(jobId, jobId)))
}

const ifMatchOf = (url: string) => calls.find((c) => c.url === url)

beforeEach(() => {
  calls.length = 0
  FakeEventSource.instances = []
  actionable = false
  vi.stubGlobal('fetch', vi.fn(backend))
  vi.stubGlobal('EventSource', FakeEventSource)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('clarification conversation', () => {
  it('Summarize asks a question; answering re-checks confidence and proceeds to the summary', async () => {
    session = makeSession()
    renderPanel()
    await waitFor(() => expect(screen.getByText(/needs clarification/)).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Summarize Scope' }))
    await finishJob('resp_clr')

    // The question is stored as a Session turn, then shown with Answer and Skip.
    await waitFor(() => expect(screen.getByLabelText('Your answer')).toBeTruthy())
    expect(screen.getAllByText(QUESTION).length).toBeGreaterThan(0)
    expect(ifMatchOf('/api/v1/session/ses_1/clarification')?.body).toEqual({ response_id: 'resp_clr' })
    expect(screen.getByRole('button', { name: 'Skip' })).toBeTruthy()

    fireEvent.change(screen.getByLabelText('Your answer'), { target: { value: 'The login form' } })
    fireEvent.click(screen.getByRole('button', { name: 'Answer' }))

    await finishJob('resp_sum')
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Scope summary' })).toBeTruthy())
    expect(screen.getByText(/goal is actionable/)).toBeTruthy()
    expect(screen.getByText('The login form')).toBeTruthy() // answered turn in the history
    const summaries = calls.filter((c) => c.url === '/api/v1/assistant/summary')
    expect(summaries).toHaveLength(2)
    expect(calls.some((c) => c.url === '/api/v1/assistant/clarify')).toBe(false)
  })

  it('Skip records the skip and shows suggestions from the Scope only', async () => {
    session = makeSession([{ clr_id: 'clr_1', question: QUESTION, refs: [], skipped: false }])
    renderPanel()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Skip' })).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: 'Skip' }))
    await finishJob('resp_sug')

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Suggestions (from Scope only)' })).toBeTruthy())
    expect(screen.getByText('Skipped')).toBeTruthy()
    expect(calls.find((c) => c.url === '/api/v1/assistant/suggestions')?.body).toEqual({ session_id: 'ses_1', finding_ref: null })
    expect(screen.queryByLabelText('Your answer')).toBeNull()
  })
})
