"""Helpers for typed SSE progress events (AD-14).

Features build events from contracts (JobProgressEvent, ...) and hand them to
sse-starlette's EventSourceResponse through `to_sse()`.
"""

from collections.abc import AsyncIterator

from contracts import SseEvent
from sse_starlette import EventSourceResponse


def to_sse(event: SseEvent) -> dict:
    """One sse-starlette message: the SSE `event:` name plus the JSON envelope."""
    return {"event": event.event, "data": event.model_dump_json()}


def event_response(events: AsyncIterator[SseEvent]) -> EventSourceResponse:
    """Stream contract events as an SSE response."""

    async def messages():
        async for event in events:
            yield to_sse(event)

    return EventSourceResponse(messages())
