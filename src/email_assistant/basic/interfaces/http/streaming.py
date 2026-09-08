import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable

from pydantic import BaseModel

from email_assistant.basic.application.services import (
    EmailClassified,
    EmailProcessingCompleted,
    EmailProcessingStarted,
    EmailReplyCreated,
    EmailResponseStarted,
    ProcessEmailEvent,
    ProcessEmailService,
)
from email_assistant.basic.domain.models import Email
from email_assistant.basic.interfaces.http.schemas import (
    EmailReplyResponse,
    StreamClassifiedData,
    StreamCompletedData,
    StreamErrorData,
    StreamRespondingData,
    StreamStartedData,
)


logger = logging.getLogger(__name__)


def encode_sse(event_name: str, payload: BaseModel) -> str:
    """Encode a validated Pydantic payload as one SSE event."""

    return f"event: {event_name}\ndata: {payload.model_dump_json()}\n\n"


def encode_process_email_event(event: ProcessEmailEvent) -> str:
    """Map an application event to its HTTP SSE representation."""

    if isinstance(event, EmailProcessingStarted):
        payload: BaseModel = StreamStartedData(record_id=event.record_id)
    elif isinstance(event, EmailClassified):
        payload = StreamClassifiedData(
            classification=event.triage.classification,
            reasoning=event.triage.reasoning,
        )
    elif isinstance(event, EmailResponseStarted):
        payload = StreamRespondingData()
    elif isinstance(event, EmailReplyCreated):
        payload = EmailReplyResponse.from_domain(event.reply)
    elif isinstance(event, EmailProcessingCompleted):
        payload = StreamCompletedData(
            action=event.result.action,
            record_id=event.result.record_id,
        )
    else:
        raise TypeError(f"Unsupported processing event: {type(event)!r}")

    return encode_sse(event.event_type.value, payload)


def encode_error_event() -> str:
    """Create a safe SSE event for an internal processing failure."""

    return encode_sse(
        "error",
        StreamErrorData(message="Email processing failed."),
    )


async def stream_process_email_events(
    service: ProcessEmailService,
    email: Email,
    is_disconnected: Callable[[], Awaitable[bool]],
) -> AsyncIterator[str]:
    """Stream serialized events and stop cleanly on client disconnect."""

    try:
        async for event in service.process_stream(email):
            if await is_disconnected():
                return

            yield encode_process_email_event(event)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Email processing failed during SSE streaming")

        if not await is_disconnected():
            yield encode_error_event()
