// TanStack Query hooks and URL helpers for /api/v1/inspection.
import { useMutation, useQuery } from '@tanstack/react-query'
import { ApiRequestError, apiGet, apiPost, apiUrl } from './client'
import type { Inspection, StartInspectionRequest, StartedJob } from './types'

export const inspectionKeys = {
  one: (inspectionId: string) => ['inspection', inspectionId] as const,
  current: (sessionId: string) => ['inspection', 'current', sessionId] as const,
}

export function useInspection(inspectionId: string | null) {
  return useQuery({
    queryKey: inspectionKeys.one(inspectionId ?? ''),
    queryFn: () => apiGet<Inspection>(`/inspection/${inspectionId}`),
    enabled: inspectionId !== null,
    staleTime: Infinity, // a stored Inspection never changes
  })
}

/** The session's latest Inspection (null when it has none yet), to restore the view after a reload. */
export function useCurrentInspection(sessionId: string | null) {
  return useQuery({
    queryKey: inspectionKeys.current(sessionId ?? ''),
    queryFn: async (): Promise<Inspection | null> => {
      try {
        return await apiGet<Inspection>(`/inspection/current?session_id=${encodeURIComponent(sessionId ?? '')}`)
      } catch (error) {
        // 404 just means "no inspection yet" for a new session: not an error state.
        if (error instanceof ApiRequestError && error.status === 404) return null
        throw error
      }
    },
    enabled: sessionId !== null,
  })
}

export function startInspection(body: StartInspectionRequest): Promise<StartedJob> {
  return apiPost<StartedJob>('/inspection', body)
}

export function useRetryInspection() {
  return useMutation({
    mutationFn: (inspectionId: string) => apiPost<StartedJob>(`/inspection/${inspectionId}/retry`),
  })
}

export function useReinspect() {
  return useMutation({
    mutationFn: (sessionId: string) => apiPost<StartedJob>('/inspection/reinspect', { session_id: sessionId }),
  })
}

export const inspectionUrls = {
  screenshot: (inspectionId: string) => apiUrl(`/inspection/${inspectionId}/screenshot`),
  crop: (inspectionId: string, findingId: string) => apiUrl(`/inspection/${inspectionId}/crops/${findingId}`),
  export: (inspectionId: string) => apiUrl(`/inspection/${inspectionId}/export`),
  events: (jobId: string) => apiUrl(`/inspection/events/${jobId}`),
}
