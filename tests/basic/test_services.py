import asyncio
import unittest

from email_assistant.basic.application.services import (
    EmailClassified,
    EmailProcessingCompleted,
    EmailProcessingStarted,
    EmailReplyCreated,
    EmailResponseStarted,
    ProcessEmailService,
    ProcessEmailEventType,
    ProcessingAction,
)
from email_assistant.basic.application.models import ProcessingStatus
from email_assistant.basic.domain.models import (
    Email,
    EmailReply,
    TriageClassification,
    TriageResult,
)
from tests.basic.fakes import InMemoryEmailProcessingRepository, TEST_USER


class TrackingClassifier:
    def __init__(
        self,
        classification: TriageClassification,
    ) -> None:
        self._classification = classification
        self.active_calls = 0
        self.maximum_active_calls = 0

    async def classify(self, email: Email) -> TriageResult:
        self.active_calls += 1
        self.maximum_active_calls = max(
            self.maximum_active_calls,
            self.active_calls,
        )

        try:
            await asyncio.sleep(0.01)
        finally:
            self.active_calls -= 1

        return TriageResult(
            classification=self._classification,
            reasoning=email.subject,
        )


class RecordingResponder:
    def __init__(self) -> None:
        self.responded_to: list[Email] = []

    async def respond(self, email: Email) -> EmailReply:
        await asyncio.sleep(0)
        self.responded_to.append(email)
        return EmailReply(
            recipient=email.author,
            subject=f"Re: {email.subject}",
            content="Thank you for your message.",
        )


def make_email(index: int) -> Email:
    return Email(
        author=f"sender-{index}@example.com",
        recipient="assistant@example.com",
        subject=f"Email {index}",
        thread="Please process this message.",
    )


class ProcessEmailServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_interrupted_stream_is_stored_as_failed(self) -> None:
        repository = InMemoryEmailProcessingRepository()
        service = ProcessEmailService(
            TrackingClassifier(TriageClassification.RESPOND),
            RecordingResponder(),
            repository,
        )
        stream = service.process_stream(make_email(1), TEST_USER)

        started = await anext(stream)
        await stream.aclose()

        record = repository.records[started.record_id]
        self.assertEqual(record.status, ProcessingStatus.FAILED)
        self.assertEqual(
            record.failure_message,
            "Email processing was interrupted.",
        )

    async def test_response_stream_emits_events_in_order(self) -> None:
        service = ProcessEmailService(
            TrackingClassifier(TriageClassification.RESPOND),
            RecordingResponder(),
            InMemoryEmailProcessingRepository(),
        )

        events = [
            event async for event in service.process_stream(make_email(1), TEST_USER)
        ]

        self.assertEqual(
            [event.event_type for event in events],
            [
                ProcessEmailEventType.STARTED,
                ProcessEmailEventType.CLASSIFIED,
                ProcessEmailEventType.RESPONDING,
                ProcessEmailEventType.REPLY_CREATED,
                ProcessEmailEventType.COMPLETED,
            ],
        )
        self.assertIsInstance(events[0], EmailProcessingStarted)
        self.assertIsInstance(events[1], EmailClassified)
        self.assertIsInstance(events[2], EmailResponseStarted)
        self.assertIsInstance(events[3], EmailReplyCreated)
        self.assertIsInstance(events[4], EmailProcessingCompleted)

    async def test_non_response_stream_skips_response_events(self) -> None:
        for classification in (
            TriageClassification.NOTIFY,
            TriageClassification.IGNORE,
        ):
            service = ProcessEmailService(
                TrackingClassifier(classification),
                RecordingResponder(),
                InMemoryEmailProcessingRepository(),
            )

            events = [
                event
                async for event in service.process_stream(make_email(1), TEST_USER)
            ]

            self.assertEqual(
                [event.event_type for event in events],
                [
                    ProcessEmailEventType.STARTED,
                    ProcessEmailEventType.CLASSIFIED,
                    ProcessEmailEventType.COMPLETED,
                ],
            )

    async def test_process_awaits_the_responder(self) -> None:
        classifier = TrackingClassifier(TriageClassification.RESPOND)
        responder = RecordingResponder()
        service = ProcessEmailService(
            classifier,
            responder,
            InMemoryEmailProcessingRepository(),
        )
        email = make_email(1)

        result = await service.process(email, TEST_USER)

        self.assertEqual(result.action, ProcessingAction.RESPONDED)
        self.assertEqual(responder.responded_to, [email])
        self.assertEqual(result.reply.recipient, email.author)

    async def test_process_many_preserves_order_and_limits_concurrency(
        self,
    ) -> None:
        classifier = TrackingClassifier(TriageClassification.IGNORE)
        service = ProcessEmailService(
            classifier,
            RecordingResponder(),
            InMemoryEmailProcessingRepository(),
            max_concurrency=2,
        )
        emails = [make_email(index) for index in range(5)]

        results = await service.process_many(emails, TEST_USER)

        self.assertEqual(
            [result.triage.reasoning for result in results],
            [email.subject for email in emails],
        )
        self.assertEqual(classifier.maximum_active_calls, 2)
        self.assertTrue(all(result.reply is None for result in results))

    def test_rejects_invalid_concurrency_limit(self) -> None:
        with self.assertRaises(ValueError):
            ProcessEmailService(
                TrackingClassifier(TriageClassification.IGNORE),
                RecordingResponder(),
                InMemoryEmailProcessingRepository(),
                max_concurrency=0,
            )


if __name__ == "__main__":
    unittest.main()
