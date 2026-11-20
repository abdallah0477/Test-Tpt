// Wires the inspection actions together: session creation, start / retry / re-inspect,
// following the job over SSE, and choosing which stored Inspection is shown.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useCallback, useState } from 'react'
import { ApiRequestError, errorMessage } from '../../api/client'
import { inspectionUrls, startInspection, useCurrentInspection, useReinspect, useRetryInspection } from '../../api/inspection'
import { createSession } from '../../api/session'
import type { DoneData, StartedJob } from '../../api/types'
import { useJobEvents } from '../../api/useJobEvents'
import { useStoredSessionId } from '../session/useStoredSessionId'

export function useInspectionFlow() {
  const queryClient = useQueryClient()
  const [sessionId, setSessionId] = useStoredSessionId()
  const [openedId, setOpenedId] = useState<string | null>(null)
  const [job, setJob] = useState<StartedJob | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const current = useCurrentInspection(sessionId)
  const shownId = openedId ?? current.data?.inspection_id ?? null

  const onDone = useCallback(
    (data: DoneData) => {
      if (data.result_kind === 'inspection') setOpenedId(data.result_id)
      setJob(null)
      void queryClient.invalidateQueries({ queryKey: ['session'] })
      void queryClient.invalidateQueries({ queryKey: ['inspection', 'current'] })
    },
    [queryClient],
  )
  const jobEvents = useJobEvents(job?.job_id ?? null, inspectionUrls.events, { onDone })

  const follow = (started: StartedJob) => {
    setActionError(null)
    setSessionId(started.session_id)
    if (started.inspection_status) {
      // Already stored without a job (e.g. Runner unreachable): show it directly, no SSE.
      setJob(null)
      setOpenedId(started.inspection_id)
      void queryClient.invalidateQueries({ queryKey: ['session'] })
      return
    }
    setJob(started)
  }

  // Start: create a session if there is none (or the stored one no longer exists), then POST /inspection.
  const start = useMutation({
    mutationFn: async (url: string) => {
      const sid = sessionId ?? (await createSession()).session_id
      try {
        return await startInspection({ session_id: sid, url })
      } catch (error) {
        if (error instanceof ApiRequestError && error.status === 404 && sessionId !== null) {
          const fresh = await createSession()
          return startInspection({ session_id: fresh.session_id, url })
        }
        throw error
      }
    },
    onSuccess: follow,
  })

  const retry = useRetryInspection()
  const reinspect = useReinspect()

  const jobRunning = job !== null && !['done', 'failed', 'closed'].includes(jobEvents.state)
  const busy = start.isPending || retry.isPending || reinspect.isPending || jobRunning

  return {
    sessionId,
    shownId,
    job,
    jobEvents,
    busy,
    actionError,
    startError: start.error ? errorMessage(start.error) : null,
    start: (url: string) => start.mutate(url),
    open: (inspectionId: string) => {
      setJob(null)
      setOpenedId(inspectionId)
    },
    retry: (inspectionId: string) =>
      retry.mutate(inspectionId, { onSuccess: follow, onError: (e) => setActionError(errorMessage(e)) }),
    reinspect: () => {
      if (sessionId === null) return
      reinspect.mutate(sessionId, { onSuccess: follow, onError: (e) => setActionError(errorMessage(e)) })
    },
  }
}
