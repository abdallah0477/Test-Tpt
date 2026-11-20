// A minimal EventSource stand-in for tests: `FakeEventSource.emit(url, payload)` delivers one named event.
type Listener = (event: MessageEvent<string>) => void

export class FakeEventSource {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSED = 2
  static instances: FakeEventSource[] = []

  readonly url: string
  readyState = FakeEventSource.OPEN
  onmessage: Listener | null = null
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  private listeners = new Map<string, Listener[]>()

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(name: string, listener: Listener) {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener])
  }

  close() {
    this.readyState = FakeEventSource.CLOSED
  }

  static find(urlPart: string): FakeEventSource | undefined {
    return FakeEventSource.instances.find((source) => source.url.includes(urlPart) && source.readyState !== FakeEventSource.CLOSED)
  }

  /** Sends a contracts envelope as a named SSE event. */
  emit(payload: { event: string } & Record<string, unknown>) {
    const message = new MessageEvent('message', { data: JSON.stringify(payload) })
    for (const listener of this.listeners.get(payload.event) ?? []) listener(message)
  }
}

export function jobDone(jobId: string, resultId: string) {
  return {
    event: 'job_done',
    job_id: jobId,
    step: 'done',
    status: 'done',
    ts: '2026-11-20T10:00:00Z',
    data: { result_kind: 'response', result_id: resultId, inspection_status: null },
  }
}
