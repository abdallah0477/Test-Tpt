// TanStack Query hooks and calls for /api/v1/session.
import { useMutation, useQuery } from '@tanstack/react-query'
import { apiGet, apiPost, apiPut } from './client'
import type { ConfidenceReport, GoalRequest, InspectionSummary, ScopeFilters, ScopeRequest, Session } from './types'

export const sessionKeys = {
  one: (sessionId: string) => ['session', sessionId] as const,
  inspections: (sessionId: string) => ['session', sessionId, 'inspections'] as const,
  /** Keyed by rev: every Session write gives a new rev, so confidence is re-read after each change. */
  confidence: (sessionId: string, rev: number) => ['session', sessionId, 'confidence', rev] as const,
}

export function createSession(): Promise<Session> {
  return apiPost<Session>('/session')
}

export function useCreateSession() {
  return useMutation({ mutationFn: createSession })
}

export function useSession(sessionId: string | null) {
  return useQuery({
    queryKey: sessionKeys.one(sessionId ?? ''),
    queryFn: () => apiGet<Session>(`/session/${sessionId}`),
    enabled: sessionId !== null,
  })
}

/** Inspection history of a session, oldest first. */
export function useSessionInspections(sessionId: string | null) {
  return useQuery({
    queryKey: sessionKeys.inspections(sessionId ?? ''),
    queryFn: () => apiGet<InspectionSummary[]>(`/session/${sessionId}/inspections`),
    enabled: sessionId !== null,
  })
}

// Writes. Each one sends the rev it is based on (If-Match); a stale rev gives 409 rev_conflict.
export function putGoal(sessionId: string, rev: number, body: GoalRequest): Promise<Session> {
  return apiPut<Session>(`/session/${sessionId}/goal`, body, rev)
}

export function putScope(sessionId: string, rev: number, body: ScopeRequest): Promise<Session> {
  return apiPut<Session>(`/session/${sessionId}/scope`, body, rev)
}

export function putFilters(sessionId: string, rev: number, body: ScopeFilters): Promise<Session> {
  return apiPut<Session>(`/session/${sessionId}/filters`, body, rev)
}

/** Confidence computed by the backend from observable signals (Story 3.4). */
export function confidenceQuery(sessionId: string, rev: number) {
  return {
    queryKey: sessionKeys.confidence(sessionId, rev),
    queryFn: () => apiGet<ConfidenceReport>(`/session/${sessionId}/confidence`),
  }
}

export function useConfidence(sessionId: string | null, rev: number | undefined) {
  return useQuery({ ...confidenceQuery(sessionId ?? '', rev ?? -1), enabled: sessionId !== null && rev !== undefined })
}

// Clarification turns (stored by v1/session; If-Match like every Session write).
export function storeClarification(sessionId: string, rev: number, responseId: string): Promise<Session> {
  return apiPost<Session>(`/session/${sessionId}/clarification`, { response_id: responseId }, rev)
}

export function answerClarification(sessionId: string, rev: number, clrId: string, text: string): Promise<Session> {
  return apiPost<Session>(`/session/${sessionId}/clarification/${clrId}/answer`, { text }, rev)
}

export function skipClarification(sessionId: string, rev: number, clrId: string): Promise<Session> {
  return apiPost<Session>(`/session/${sessionId}/clarification/${clrId}/skip`, {}, rev)
}
