// /api/v1/usage: model call records of a Session, grouped per response (Story 3.5).
import { useQuery } from '@tanstack/react-query'
import { apiGet, apiUrl } from './client'
import type { SessionUsage } from './types'

export const usageKeys = { session: (sessionId: string) => ['usage', sessionId] as const }

export function useSessionUsage(sessionId: string | null) {
  return useQuery({
    queryKey: usageKeys.session(sessionId ?? ''),
    queryFn: () => apiGet<SessionUsage>(`/usage/${sessionId}`),
    enabled: sessionId !== null,
  })
}

export const usageExportUrl = (sessionId: string) => apiUrl(`/usage/${sessionId}/export`)
