import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
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

        async with self._concurrency_limiter:
            return await self._process_email(email)

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

    async def _process_email(self, email: Email) -> ProcessEmailResult:
        """Process one email after a concurrency slot has been acquired."""

        triage_result = await self._classifier.classify(email)
        reply = None

        if triage_result.classification is TriageClassification.RESPOND:
            reply = await self._responder.respond(email)
            action = ProcessingAction.RESPONDED

        elif triage_result.classification is TriageClassification.NOTIFY:
            action = ProcessingAction.NOTIFICATION_REQUIRED

        elif triage_result.classification is TriageClassification.IGNORE:
            action = ProcessingAction.IGNORED

        else:
            raise ValueError(
                f"Unsupported classification: {triage_result.classification}"
            )

        return ProcessEmailResult(
            triage=triage_result,
            action=action,
            reply=reply,
        )
