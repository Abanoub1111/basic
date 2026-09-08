import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID
from email_assistant.basic.domain.users import User, UserRole
from email_assistant.basic.application.auth import AuthenticationError

from email_assistant.basic.application.models import (
    EmailProcessingRecord,
    ProcessEmailResult,
    ProcessingAction,
)
from email_assistant.basic.application.ports import (
    EmailClassifier,
    EmailProcessingRepository,
    EmailResponder,
)
from email_assistant.basic.domain.models import (
    Email,
    EmailReply,
    TriageClassification,
    TriageResult,
)


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

    record_id: UUID
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
        repository: EmailProcessingRepository,
        max_concurrency: int = 3,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")

        self._classifier = classifier
        self._responder = responder
        self._repository = repository
        self._concurrency_limiter = asyncio.Semaphore(max_concurrency)

    async def process(self, email: Email, user: User) -> ProcessEmailResult:
        """Classify an email and perform the appropriate action."""

        completed_result = None

        async for event in self.process_stream(email, user):
            if isinstance(event, EmailProcessingCompleted):
                completed_result = event.result

        if completed_result is None:
            raise RuntimeError("Email processing ended without a result")

        return completed_result

    async def process_many(
        self,
        emails: Sequence[Email],
        user: User,
    ) -> list[ProcessEmailResult]:
        """Process emails concurrently while respecting the shared limit."""

        return list(
            await asyncio.gather(
                *(self.process(email, user) for email in emails)
            )
        )

    async def process_stream(
        self,
        email: Email,
        user: User,
    ) -> AsyncIterator[ProcessEmailEvent]:
        """Yield typed progress events while processing one email."""

        if not user.is_active:
            raise AuthenticationError()
        async with self._concurrency_limiter:
            record = await self._repository.create(email, user.id)
            finalized = False

            try:
                yield EmailProcessingStarted(record_id=record.id)
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

                result = ProcessEmailResult(
                    record_id=record.id,
                    triage=triage_result,
                    action=action,
                    reply=reply,
                )
                await self._repository.complete(record.id, result)
                finalized = True
                yield EmailProcessingCompleted(result=result)
            except Exception:
                try:
                    await self._repository.fail(
                        record.id,
                        "Email processing failed.",
                    )
                finally:
                    finalized = True
                raise
            finally:
                if not finalized:
                    await asyncio.shield(
                        self._repository.fail(
                            record.id,
                            "Email processing was interrupted.",
                        )
                    )


class EmailHistoryNotFoundError(LookupError):
    """Raised when a requested history record does not exist."""


class EmailHistoryService:
    """Read and delete stored email-processing history."""

    def __init__(self, repository: EmailProcessingRepository) -> None:
        self._repository = repository

    @staticmethod
    def _owner_scope(user: User) -> UUID | None:
        if not user.is_active:
            raise AuthenticationError()
        return None if user.role is UserRole.ADMIN else user.id

    async def list(
        self,
        skip: int,
        limit: int,
        user: User,
    ) -> list[EmailProcessingRecord]:
        return await self._repository.list(skip=skip, limit=limit, owner_id=self._owner_scope(user))

    async def get(self, record_id: UUID, user: User) -> EmailProcessingRecord:
        record = await self._repository.get(record_id, owner_id=self._owner_scope(user))
        if record is None:
            raise EmailHistoryNotFoundError(str(record_id))
        return record

    async def delete(self, record_id: UUID, user: User) -> None:
        if not await self._repository.delete(record_id, owner_id=self._owner_scope(user)):
            raise EmailHistoryNotFoundError(str(record_id))
