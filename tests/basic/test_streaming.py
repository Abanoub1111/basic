from tests.basic.fakes import TEST_USER, FakeAuthService
import json
import unittest
from typing import cast
from uuid import uuid4

from fastapi.testclient import TestClient

from email_assistant.basic.application.services import (
    EmailHistoryService,
    EmailClassified,
    EmailProcessingCompleted,
    EmailProcessingStarted,
    ProcessEmailResult,
    ProcessEmailService,
    ProcessingAction,
)
from email_assistant.basic.domain.models import (
    Email,
    TriageClassification,
    TriageResult,
)
from email_assistant.basic.interfaces.http.app import create_app
from email_assistant.basic.interfaces.http.streaming import (
    encode_process_email_event,
    stream_process_email_events,
)


def make_email() -> Email:
    return Email(
        author="sender@example.com",
        recipient="assistant@example.com",
        subject="Project meeting",
        thread="Can we meet tomorrow?",
    )


async def connected() -> bool:
    return False


class FailingStreamService:
    async def process_stream(self, email: Email, user):
        yield EmailProcessingStarted(record_id=uuid4())
        raise RuntimeError("Provider failure")


class SuccessfulStreamService:
    async def process_stream(self, email: Email, user):
        record_id = uuid4()
        triage = TriageResult(
            classification=TriageClassification.IGNORE,
            reasoning="No action is required.",
        )
        yield EmailProcessingStarted(record_id=record_id)
        yield EmailClassified(triage=triage)
        yield EmailProcessingCompleted(
            result=ProcessEmailResult(
                record_id=record_id,
                triage=triage,
                action=ProcessingAction.IGNORED,
            )
        )


class SseEncodingTests(unittest.TestCase):
    def test_classified_event_has_valid_sse_framing_and_json(self) -> None:
        encoded = encode_process_email_event(
            EmailClassified(
                triage=TriageResult(
                    classification=TriageClassification.RESPOND,
                    reasoning="A direct response was requested.",
                )
            )
        )

        lines = encoded.splitlines()

        self.assertEqual(lines[0], "event: classified")
        self.assertEqual(
            json.loads(lines[1].removeprefix("data: ")),
            {
                "classification": "respond",
                "reasoning": "A direct response was requested.",
            },
        )
        self.assertTrue(encoded.endswith("\n\n"))

    def test_all_email_endpoints_remain_registered(self) -> None:
        service = cast(ProcessEmailService, object())
        history = cast(EmailHistoryService, object())
        paths = create_app(service, history, FakeAuthService()).openapi()["paths"]

        self.assertIn("/emails/process", paths)
        self.assertIn("/emails/process/batch", paths)
        self.assertIn("/emails/process/stream", paths)

    def test_stream_endpoint_returns_event_stream_content(self) -> None:
        service = cast(ProcessEmailService, SuccessfulStreamService())
        history = cast(EmailHistoryService, object())
        client = TestClient(create_app(service, history, FakeAuthService()))

        response = client.post(
            "/emails/process/stream",
            headers={"Authorization": "Bearer test"},
            json={
                "author": "newsletter@example.com",
                "to": "assistant@example.com",
                "subject": "Weekly newsletter",
                "email_thread": "No response is required.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.headers["content-type"].startswith("text/event-stream")
        )
        self.assertIn("event: started", response.text)
        self.assertIn("event: classified", response.text)
        self.assertIn("event: completed", response.text)


class SseStreamingTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_becomes_a_safe_error_event(self) -> None:
        service = cast(ProcessEmailService, FailingStreamService())

        events = [
            event
            async for event in stream_process_email_events(
                service,
                make_email(),
                connected,
                TEST_USER,
            )
        ]

        self.assertTrue(events[0].startswith("event: started\ndata: "))
        self.assertEqual(
            events[1],
            "event: error\ndata: {\"message\":\"Email processing failed.\"}\n\n",
        )

    async def test_disconnect_stops_before_sending_an_event(self) -> None:
        service = cast(ProcessEmailService, FailingStreamService())

        async def disconnected() -> bool:
            return True

        events = [
            event
            async for event in stream_process_email_events(
                service,
                make_email(),
                disconnected,
                TEST_USER,
            )
        ]

        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
