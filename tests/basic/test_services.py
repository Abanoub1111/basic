import asyncio
import unittest

from email_assistant.basic.application.services import (
    ProcessEmailService,
    ProcessingAction,
)
from email_assistant.basic.domain.models import (
    Email,
    EmailReply,
    TriageClassification,
    TriageResult,
)


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
    async def test_process_awaits_the_responder(self) -> None:
        classifier = TrackingClassifier(TriageClassification.RESPOND)
        responder = RecordingResponder()
        service = ProcessEmailService(classifier, responder)
        email = make_email(1)

        result = await service.process(email)

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
            max_concurrency=2,
        )
        emails = [make_email(index) for index in range(5)]

        results = await service.process_many(emails)

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
                max_concurrency=0,
            )


if __name__ == "__main__":
    unittest.main()
