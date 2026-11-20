// Reusable SSE hook: follows one backend job and parses the contracts event envelope
// {event, job_id, step, status, ts, data} (AD-14).
import { useEffect, useRef, useState } from 'react'
import type { DoneData, ErrorBody, SseEvent } from './types'

export const SSE_EVENT_NAMES = ['job_queued', 'job_progress', 'job_done', 'job_failed'] as const

export type JobStreamState = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'done' | 'failed' | 'closed'

export interface JobEvents {
  state: JobStreamState
  events: SseEvent[]
  latest: SseEvent | null
  done: DoneData | null
  failure: ErrorBody | null
}

export interface JobEventCallbacks {
  onDone?: (data: DoneData) => void
  onFailed?: (error: ErrorBody) => void
}

/** Parses one SSE `data:` payload. Returns null for anything that is not an envelope. */
export function parseSseEvent(raw: string): SseEvent | null {
  try {
    const value = JSON.parse(raw) as Partial<SseEvent> | null
    if (!value || typeof value.event !== 'string' || typeof value.job_id !== 'string') return null
    if (!(SSE_EVENT_NAMES as readonly string[]).includes(value.event)) return null
    return value as SseEvent
  } catch {
    return null
  }
}

const IDLE: JobEvents = { state: 'idle', events: [], latest: null, done: null, failure: null }

/** Opens an EventSource for `jobId` (null = nothing to follow) and closes it on job_done / job_failed. */
export function useJobEvents(
  jobId: string | null,
  url: (jobId: string) => string,
  callbacks: JobEventCallbacks = {},
): JobEvents {
  // State is tagged with its jobId, so switching jobs starts from a clean slate without a reset effect.
  const [tagged, setTagged] = useState<{ jobId: string | null; value: JobEvents }>({ jobId: null, value: IDLE })
  const callbacksRef = useRef(callbacks)
  useEffect(() => {
    callbacksRef.current = callbacks
  })

  useEffect(() => {
    if (jobId === null) return
    const source = new EventSource(url(jobId))
    const update = (fn: (prev: JobEvents) => JobEvents) =>
      setTagged((prev) => ({ jobId, value: fn(prev.jobId === jobId ? prev.value : { ...IDLE, state: 'connecting' }) }))

    const handle = (message: MessageEvent<string>) => {
      const event = parseSseEvent(message.data)
      if (!event || event.job_id !== jobId) return
      update((prev) => {
        const next: JobEvents = { ...prev, state: 'open', events: [...prev.events, event], latest: event }
        if (event.event === 'job_done') return { ...next, state: 'done', done: event.data }
        if (event.event === 'job_failed') return { ...next, state: 'failed', failure: event.data.error }
        return next
      })
      if (event.event === 'job_done') {
        source.close()
        callbacksRef.current.onDone?.(event.data)
      } else if (event.event === 'job_failed') {
        source.close()
        callbacksRef.current.onFailed?.(event.data.error)
      }
    }

    // The backend may send named events (`event: job_progress`) or unnamed ones; listen for both.
    source.onmessage = handle
    for (const name of SSE_EVENT_NAMES) source.addEventListener(name, handle as EventListener)
    source.onopen = () => update((prev) => ({ ...prev, state: 'open' }))
    source.onerror = () =>
      update((prev) => ({
        ...prev,
        // EventSource reconnects by itself unless the browser gave up (CLOSED).
        state: source.readyState === EventSource.CLOSED ? 'closed' : 'reconnecting',
      }))

    return () => source.close()
  }, [jobId, url])

  if (jobId === null) return IDLE
  return tagged.jobId === jobId ? tagged.value : { ...IDLE, state: 'connecting' }
}
