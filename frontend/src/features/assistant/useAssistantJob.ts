// Runs one assistant job at a time: start -> follow SSE -> load the stored response.
// Uses job_done.data.result_id (the response id) to fetch the result.
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { assistantEventsUrl, responseQuery } from '../../api/assistant'
import { errorCode, errorMessage } from '../../api/client'
import type { AssistantJob, AssistantResponse } from '../../api/types'
import { usageKeys } from '../../api/usage'
import { useJobEvents } from '../../api/useJobEvents'

const FRIENDLY: Record<string, string> = {
  scope_empty: 'Select Findings into the Scope first.',
  no_inspection: 'Inspect a page first.',
  model_unavailable: 'The local model is not reachable. Check that Ollama is running, then try again.',
  model_error: 'The model returned an error. Try again.',
}

export function assistantError(error: unknown): string {
  const code = errorCode(error)
  return (code && FRIENDLY[code]) || errorMessage(error)
}

export function useAssistantJob(sessionId: string | null, onResponse?: (response: AssistantResponse) => void | Promise<void>) {
  const queryClient = useQueryClient()
  const [job, setJob] = useState<AssistantJob | null>(null)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const events = useJobEvents(job?.job_id ?? null, assistantEventsUrl, {
    onDone: async (data) => {
      if (!sessionId) return
      try {
        const response = await queryClient.fetchQuery(responseQuery(data.result_id, sessionId))
        void queryClient.invalidateQueries({ queryKey: usageKeys.session(sessionId) })
        await onResponse?.(response)
      } catch (e) {
        setError(assistantError(e))
      }
    },
    onFailed: (failure) => setError(FRIENDLY[failure.code] ?? `${failure.message} (${failure.code})`),
  })

  async function start(fn: () => Promise<AssistantJob>): Promise<AssistantJob | null> {
    setError(null)
    setStarting(true)
    try {
      const started = await fn()
      setJob(started)
      return started
    } catch (e) {
      setError(assistantError(e))
      return null
    } finally {
      setStarting(false)
    }
  }

  const running = starting || (job !== null && !['done', 'failed', 'closed'].includes(events.state))
  return { job, events, running, error, setError, start }
}
