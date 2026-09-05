import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from enum import Enum

from email_assistant.basic.application.ports import (
    EmailClassifier,
    EmailResponder,
)
from email_assistant.basic.domain.models import (
    Email,
    EmailReply,
    TriageClassification,
    TriageResult,
)


class ProcessingAction(str, Enum):
    """Action taken after an email has been classified."""

    RESPONDED = "responded"
    NOTIFICATION_REQUIRED = "notification_required"
    IGNORED = "ignored"


@dataclass(frozen=True)
class ProcessEmailResult:
    """Result returned after processing an email."""

    triage: TriageResult
    action: ProcessingAction
    reply: EmailReply | None = None


class ProcessEmailEventType(str, Enum):
    """Events emitted while an email is being processed."""

    STARTED = "started"
    CLASSIFIED = "classified"
    RESPONDING = "responding"
    REPLY_CREATED = "reply_created"
    COMPLETED = "completed"


@dataclass(frozen=True)
class EmailProcessingStarted:
    """Signal that processing has acquired a concurrency slot."""

    event_type: ProcessEmailEventType = field(
        default=ProcessEmailEventType.STARTED,
        init=False,
    )


@dataclass(frozen=True)
class EmailClassified:
    """Report the completed triage decision."""

    triage: TriageResult
    event_type: ProcessEmailEventType = field(
        default=ProcessEmailEventType.CLASSIFIED,
        init=False,
    )


@dataclass(frozen=True)
class EmailResponseStarted:
    """Signal that the response workflow has started."""

    event_type: ProcessEmailEventType = field(
        default=ProcessEmailEventType.RESPONDING,
        init=False,
    )


@dataclass(frozen=True)
class EmailReplyCreated:
    """Report the reply drafted by the response workflow."""

    reply: EmailReply
    event_type: ProcessEmailEventType = field(
        default=ProcessEmailEventType.REPLY_CREATED,
        init=False,
    )


@dataclass(frozen=True)
class EmailProcessingCompleted:
    """Report the final processing result."""

    result: ProcessEmailResult
    event_type: ProcessEmailEventType = field(
        default=ProcessEmailEventType.COMPLETED,
        init=False,
    )


ProcessEmailEvent = (
    EmailProcessingStarted
    | EmailClassified
    | EmailResponseStarted
    | EmailReplyCreated
    | EmailProcessingCompleted
)


class ProcessEmailService:
    """Coordinate email classification and response."""

    def __init__(
        self,
        classifier: EmailClassifier,
        responder: EmailResponder,
        max_concurrency: int = 3,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")

        self._classifier = classifier
        self._responder = responder
        self._concurrency_limiter = asyncio.Semaphore(max_concurrency)

    async def process(self, email: Email) -> ProcessEmailResult:
        """Classify an email and perform the appropriate action."""

        completed_result = None

        async for event in self.process_stream(email):
            if isinstance(event, EmailProcessingCompleted):
                completed_result = event.result

        if completed_result is None:
            raise RuntimeError("Email processing ended without a result")

        return completed_result

    async def process_many(
        self,
        emails: Sequence[Email],
    ) -> list[ProcessEmailResult]:
        """Process emails concurrently while respecting the shared limit."""

        return list(
            await asyncio.gather(
                *(self.process(email) for email in emails)
            )
        )

    async def process_stream(
        self,
        email: Email,
    ) -> AsyncIterator[ProcessEmailEvent]:
        """Yield typed progress events while processing one email."""

        async with self._concurrency_limiter:
            yield EmailProcessingStarted()

            triage_result = await self._classifier.classify(email)
            yield EmailClassified(triage=triage_result)

            reply = None

            if triage_result.classification is TriageClassification.RESPOND:
                yield EmailResponseStarted()
                reply = await self._responder.respond(email)
                yield EmailReplyCreated(reply=reply)
                action = ProcessingAction.RESPONDED

            elif triage_result.classification is TriageClassification.NOTIFY:
                action = ProcessingAction.NOTIFICATION_REQUIRED

            elif triage_result.classification is TriageClassification.IGNORE:
                action = ProcessingAction.IGNORED

            else:
                raise ValueError(
                    "Unsupported classification: "
                    f"{triage_result.classification}"
                )

            yield EmailProcessingCompleted(
                result=ProcessEmailResult(
                    triage=triage_result,
                    action=action,
                    reply=reply,
                )
            )
