import { useState } from 'react'
import { startSuggestions } from '../../api/assistant'
import type { FindingRef } from '../../api/types'
import { AssistantProgress } from './AssistantProgress'
import { ResponseCard } from './ResponseCard'
import { useAssistantJob } from './useAssistantJob'

/** Detail panel "Assistant" area: testing suggestions for one Finding (Story 3.3). */
export function FindingSuggestions({ sessionId, findingRef }: { sessionId: string | null; findingRef: FindingRef }) {
  const [responseId, setResponseId] = useState<string | null>(null)
  const job = useAssistantJob(sessionId, (response) => setResponseId(response.response_id))
  return (
    <div className="finding-suggestions">
      <button
        type="button"
        className="btn"
        disabled={!sessionId || job.running}
        onClick={() => sessionId && job.start(() => startSuggestions(sessionId, findingRef))}
      >
        Get suggestions for this element
      </button>
      <AssistantProgress job={job.events} />
      {job.error && (
        <p className="field-error" role="alert">
          {job.error}
        </p>
      )}
      {sessionId && responseId && <ResponseCard responseId={responseId} sessionId={sessionId} label="Suggestions for this element" />}
    </div>
  )
}
