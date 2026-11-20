import { describe, expect, it } from 'vitest'
import { parseSseEvent } from './useJobEvents'

describe('parseSseEvent', () => {
  it('parses a contracts envelope', () => {
    const event = parseSseEvent(
      JSON.stringify({
        event: 'job_done',
        job_id: 'ins_1',
        step: 'store',
        status: 'done',
        ts: '2026-11-20T10:00:00Z',
        data: { result_kind: 'inspection', result_id: 'ins_1', inspection_status: 'complete' },
      }),
    )
    expect(event?.event).toBe('job_done')
  })

  it('ignores anything that is not an envelope', () => {
    expect(parseSseEvent('not json')).toBeNull()
    expect(parseSseEvent('{"event":"other","job_id":"x"}')).toBeNull()
    expect(parseSseEvent('{"job_id":"x"}')).toBeNull()
  })
})
