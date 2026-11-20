import { stepLabel } from './assistantText'
import type { JobEvents } from '../../api/useJobEvents'

export function AssistantProgress({ job }: { job: JobEvents }) {
  if (job.state === 'idle') return null
  return (
    <ol className="progress-steps assistant-progress" aria-label="Assistant progress" aria-live="polite">
      {job.events.map((event, index) => (
        <li key={index} className={`progress-step step-${event.status}`}>
          {stepLabel(event)}
        </li>
      ))}
      {job.events.length === 0 && <li className="muted">Starting…</li>}
    </ol>
  )
}
