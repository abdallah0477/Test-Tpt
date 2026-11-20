// Calls and hooks for /api/v1/assistant. Flow: POST summary | clarify | suggestions -> {job_id}
// -> SSE /events/{job_id} -> job_done.data.result_id -> GET /responses/{result_id}?session_id=
import { useQuery } from '@tanstack/react-query'
import { apiGet, apiPost, apiUrl } from './client'
import type { AssistantJob, AssistantResponse, FindingRef } from './types'

export function startSummary(sessionId: string): Promise<AssistantJob> {
  return apiPost<AssistantJob>('/assistant/summary', { session_id: sessionId })
}

export function startClarify(sessionId: string): Promise<AssistantJob> {
  return apiPost<AssistantJob>('/assistant/clarify', { session_id: sessionId })
}

/** With `findingRef`: suggestions for one Finding; without: for the Scope (after a skip). */
export function startSuggestions(sessionId: string, findingRef?: FindingRef): Promise<AssistantJob> {
  return apiPost<AssistantJob>('/assistant/suggestions', { session_id: sessionId, finding_ref: findingRef ?? null })
}

export const assistantEventsUrl = (jobId: string) => apiUrl(`/assistant/events/${jobId}`)

export function responseQuery(responseId: string, sessionId: string) {
  return {
    queryKey: ['assistant', 'response', responseId] as const,
    queryFn: () =>
      apiGet<AssistantResponse>(`/assistant/responses/${responseId}?session_id=${encodeURIComponent(sessionId)}`),
    staleTime: Infinity, // responses are written once
  }
}

export function useAssistantResponse(responseId: string, sessionId: string) {
  return useQuery(responseQuery(responseId, sessionId))
}
