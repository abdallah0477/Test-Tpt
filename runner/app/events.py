"""Fan-out of contracts SSE events from the worker thread to /events clients.

The worker thread calls `publish()`. Every connected client has its own
asyncio queue; events are handed over with `call_soon_threadsafe`. The last
few hundred events are kept so a client that connects late (for example right
after POST /inspect) still sees the job's earlier events.
"""

import asyncio
import threading
from collections import deque

from contracts import SseEvent

HISTORY_SIZE = 500


class EventBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._history: deque[SseEvent] = deque(maxlen=HISTORY_SIZE)

    def publish(self, event: SseEvent) -> None:
        with self._lock:
            self._history.append(event)
            subscribers = list(self._subscribers)
        for loop, queue in subscribers:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError:  # the client's loop is closed
                pass

    def subscribe(self, job_id: str | None = None) -> tuple[asyncio.Queue, list[SseEvent]]:
        """Register a client; returns its queue and the matching past events to replay."""
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers.append((asyncio.get_running_loop(), queue))
            past = [e for e in self._history if job_id is None or e.job_id == job_id]
        return queue, past

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers = [(lp, q) for lp, q in self._subscribers if q is not queue]

    def history(self, job_id: str | None = None) -> list[SseEvent]:
        with self._lock:
            return [e for e in self._history if job_id is None or e.job_id == job_id]
