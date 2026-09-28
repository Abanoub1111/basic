import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from email_assistant.basic.application.auth import AuthenticationError
from email_assistant.basic.application.services import ProcessEmailService, EmailHistoryService
from email_assistant.basic.application.usage import UsageLimits, UsageCharge, RateLimitExceeded
from email_assistant.basic.domain.models import TriageClassification
from email_assistant.basic.infrastructure.usage_counter import InMemoryUsageCounter
from email_assistant.basic.interfaces.http.app import create_app
from tests.basic.fakes import TEST_USER, InMemoryEmailProcessingRepository
from tests.basic.test_services import TrackingClassifier, RecordingResponder


class CounterTests(unittest.TestCase):
    def test_weighted_window_expires_without_sleeping(self):
        now = [100.0]
        counter = InMemoryUsageCounter(lambda: now[0])
        counter.consume([UsageCharge("user", 3, 2)])
        now[0] += 20
        counter.consume([UsageCharge("user", 3)])
        with self.assertRaises(RateLimitExceeded) as failure:
            counter.consume([UsageCharge("user", 3, 2)])
        self.assertEqual(failure.exception.retry_after, 40)
        now[0] += 40
        counter.consume([UsageCharge("user", 3, 2)])

    def test_concurrent_admissions_do_not_exceed_limit(self):
        counter = InMemoryUsageCounter(lambda: 0)
        def attempt(_):
            try:
                counter.consume([UsageCharge("user", 5)])
                return True
            except RateLimitExceeded:
                return False
        with ThreadPoolExecutor(max_workers=10) as pool:
            self.assertEqual(sum(pool.map(attempt, range(30))), 5)

    def test_login_buckets_are_independent_and_rejection_is_atomic(self):
        usage = UsageLimits(InMemoryUsageCounter(lambda: 0), login_ip_per_minute=2,
                            login_email_per_minute=1)
        usage.login("ip-a", " FIRST@example.com ")
        with self.assertRaises(RateLimitExceeded):
            usage.login("ip-b", "first@example.com")
        # The rejected attempt must not spend ip-b's quota.
        usage.login("ip-b", "second@example.com")
        usage.login("ip-b", "third@example.com")
        with self.assertRaises(RateLimitExceeded):
            usage.login("ip-b", "fourth@example.com")


class HttpUsageTests(unittest.TestCase):
    def setUp(self):
        self.now = [0.0]
        self.repository = InMemoryEmailProcessingRepository()
        self.auth = AsyncMock()
        other = replace(TEST_USER, id=uuid4())
        async def current_user(token):
            return other if token == "other" else TEST_USER
        self.auth.current_user.side_effect = current_user
        self.auth.login.side_effect = AuthenticationError()
        self.usage = UsageLimits(InMemoryUsageCounter(lambda: self.now[0]),
                                 emails_per_minute=3, login_ip_per_minute=2,
                                 login_email_per_minute=1)
        app = create_app(
            ProcessEmailService(TrackingClassifier(TriageClassification.IGNORE),
                                RecordingResponder(), self.repository),
            EmailHistoryService(self.repository), self.auth, self.usage)
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer user"}
        self.body = {"author": "sender@example.com", "to": "recipient@example.com",
                     "subject": "Test", "email_thread": "Test message"}

    def test_shared_quota_weighted_batch_stream_and_user_isolation(self):
        self.assertEqual(self.client.post("/emails/process", json=self.body, headers=self.headers).status_code, 200)
        rejected = self.client.post("/emails/process/batch", json={"emails": [self.body] * 3}, headers=self.headers)
        self.assertEqual(rejected.status_code, 429)
        self.assertEqual(rejected.headers["Retry-After"], "60")
        self.assertEqual(len(self.repository.records), 1)
        self.assertEqual(self.client.post("/emails/process/batch", json={"emails": [self.body] * 2}, headers=self.headers).status_code, 200)
        stream = self.client.post("/emails/process/stream", json=self.body, headers=self.headers)
        self.assertEqual(stream.status_code, 429)
        self.assertIn("application/json", stream.headers["content-type"])
        self.assertEqual(len(self.repository.records), 3)
        self.assertEqual(self.client.post("/emails/process", json=self.body,
                                         headers={"Authorization": "Bearer other"}).status_code, 200)
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.now[0] = 60
        stream = self.client.post("/emails/process/stream", json=self.body, headers=self.headers)
        self.assertEqual(stream.status_code, 200)
        self.assertIn("event: completed", stream.text)

    def test_login_limit_runs_before_password_verification(self):
        body = {"email": "a@example.com", "password": "wrong"}
        self.assertEqual(self.client.post("/auth/login", json=body).status_code, 401)
        self.assertEqual(self.client.post("/auth/login", json=body).status_code, 429)
        self.assertEqual(self.auth.login.await_count, 1)
        self.assertEqual(self.client.post("/auth/login", json={**body, "email": "b@example.com"}).status_code, 401)
        self.assertEqual(self.client.post("/auth/login", json={**body, "email": "c@example.com"}).status_code, 429)
        self.assertEqual(self.auth.login.await_count, 2)

    def test_invalid_and_unauthenticated_requests_do_not_spend_email_quota(self):
        self.assertEqual(self.client.post("/emails/process", json=self.body).status_code, 401)
        self.assertEqual(self.client.post("/emails/process", json={}, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.post("/emails/process/batch", json={"emails": [self.body] * 4}, headers=self.headers).status_code, 422)
        self.assertEqual(self.client.post("/emails/process/batch", json={"emails": [self.body] * 3}, headers=self.headers).status_code, 200)
