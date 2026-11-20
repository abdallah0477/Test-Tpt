// Goal, Scope and filter edits for one Session, with optimistic concurrency.
// Every write sends the Session.rev it is based on. On 409 rev_conflict the Session is
// reloaded and the tester is asked to retry; nothing is overwritten silently.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { errorMessage, isRevConflict } from '../../api/client'
import { putFilters, putGoal, putScope, sessionKeys, useSession } from '../../api/session'
import type { ScopeFilters, Session } from '../../api/types'
import { toRefs } from './scopeOps'

export const CONFLICT_MESSAGE = 'This session was updated elsewhere. It has been reloaded, please retry.'

/** One write: takes the current Session and returns the new stored Session. */
export type Write = (session: Session) => Promise<Session>

export function useSessionEditing(sessionId: string | null) {
  const queryClient = useQueryClient()
  const session = useSession(sessionId)
  const [message, setMessage] = useState<string | null>(null)

  const write = useMutation({
    mutationFn: async (fn: Write) => {
      const current = session.data
      if (!current) throw new Error('The session is not loaded yet.')
      return fn(current)
    },
    onMutate: () => setMessage(null),
    onSuccess: (stored) => queryClient.setQueryData(sessionKeys.one(stored.session_id), stored),
    onError: (error) => {
      if (isRevConflict(error)) {
        setMessage(CONFLICT_MESSAGE)
        if (sessionId) void queryClient.invalidateQueries({ queryKey: sessionKeys.one(sessionId), exact: true })
      } else {
        setMessage(`Could not save: ${errorMessage(error)}`)
      }
    },
  })

  return {
    session: session.data,
    isLoading: session.isPending && sessionId !== null,
    saving: write.isPending,
    message,
    saveGoal: (text: string) => write.mutate((s) => putGoal(s.session_id, s.rev ?? 0, { text })),
    setScope: (inspectionId: string, ids: string[]) =>
      write.mutate((s) => putScope(s.session_id, s.rev ?? 0, { inspection_id: inspectionId, refs: toRefs(inspectionId, ids) })),
    /** Stores the filters, then replaces the Scope with the matching Findings. */
    applyFilters: (inspectionId: string, filters: ScopeFilters, ids: string[]) =>
      write.mutate(async (s) => {
        const saved = await putFilters(s.session_id, s.rev ?? 0, filters)
        queryClient.setQueryData(sessionKeys.one(saved.session_id), saved) // keep the new rev even if the next PUT fails
        return putScope(saved.session_id, saved.rev ?? 0, { inspection_id: inspectionId, refs: toRefs(inspectionId, ids) })
      }),
    saveFilters: (filters: ScopeFilters) => write.mutate((s) => putFilters(s.session_id, s.rev ?? 0, filters)),
    /** Any other Session write (e.g. clarification turns); resolves with the stored Session, rejects on error. */
    writeAsync: (fn: Write) => write.mutateAsync(fn),
    clearMessage: () => setMessage(null),
  }
}

export type SessionEditing = ReturnType<typeof useSessionEditing>
