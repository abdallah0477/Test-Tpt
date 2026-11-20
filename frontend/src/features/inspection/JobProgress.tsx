import type { JobEvents } from '../../api/useJobEvents'
import type { SseEvent } from '../../api/types'

function describe(event: SseEvent): string {
  switch (event.event) {
    case 'job_queued':
      return event.data.position === 0 ? 'Queued, starting next' : `Queued (${event.data.position} ahead)`
    case 'job_progress': {
      const { message, done, total } = event.data
      return done != null && total != null ? `${message} (${done}/${total})` : message
    }
    case 'job_done':
      return 'Done'
    case 'job_failed':
      return `Failed: ${event.data.error.message}`
  }
}

const STREAM_NOTE: Partial<Record<JobEvents['state'], string>> = {
  connecting: 'Connecting to progress stream…',
  reconnecting: 'Progress stream interrupted, reconnecting…',
  closed: 'Progress stream closed before the job finished.',
}

/** Live progress steps of one job, from the SSE stream. */
export function JobProgress({ job }: { job: JobEvents }) {
  const note = STREAM_NOTE[job.state]
  return (
    <section className="progress" aria-label="Inspection progress">
      <h2 className="section-title">Progress</h2>
      <ol className="progress-steps" aria-live="polite">
        {job.events.map((event, index) => (
          <li key={index} className={`progress-step step-${event.status}`}>
            <span className="step-name">{event.step}</span> {describe(event)}
          </li>
        ))}
      </ol>
      {note && <p className="muted">{note}</p>}
    </section>
  )
}
