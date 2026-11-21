import { useAssistantResponse } from '../../api/assistant'
import { errorMessage } from '../../api/client'
import type { AssistantResponse, ModelCallRecord, ResponseUsage } from '../../api/types'
import { useSessionUsage } from '../../api/usage'
import { Icon } from '../../shell/Icon'
import { UsageBadge } from '../usage/UsageBadge'
import { MODE_LABEL, validationText } from './assistantText'
import { ResponseSectionsView } from './ResponseSections'

interface ResponseViewProps {
  response: AssistantResponse
  label?: string
  usage?: ResponseUsage
  records?: ModelCallRecord[]
}

/** One validated assistant answer, always labelled as assistant output. */
export function ResponseView({ response, label, usage, records = [] }: ResponseViewProps) {
  return (
    <article className="response-card" aria-label={label ?? MODE_LABEL[response.mode]}>
      <header className="response-head">
        <span className="badge assistant-tag">Assistant output</span>
        <h3>{label ?? MODE_LABEL[response.mode]}</h3>
      </header>
      <p className={`validation validation-${response.validation.outcome}`}>
        <Icon name={response.validation.outcome === 'blocked' ? 'alert' : 'check'} /> {validationText(response)}
      </p>
      {response.withheld_notice && (
        <p className="withheld" role="note">
          <strong>Withheld:</strong> {response.withheld_notice}
        </p>
      )}
      <ResponseSectionsView sections={response.sections} />
      <UsageBadge usage={usage} records={records} />
    </article>
  )
}

/** Loads a stored response and its usage, then renders it. */
export function ResponseCard({ responseId, sessionId, label }: { responseId: string; sessionId: string; label?: string }) {
  const response = useAssistantResponse(responseId, sessionId)
  const usage = useSessionUsage(sessionId)
  if (response.isPending) return <p className="muted">Loading response…</p>
  if (response.isError) return <p className="field-error">Could not load the response: {errorMessage(response.error)}</p>
  return (
    <ResponseView
      response={response.data}
      label={label}
      usage={usage.data?.responses.find((r) => r.response_id === responseId)}
      records={usage.data?.records}
    />
  )
}
