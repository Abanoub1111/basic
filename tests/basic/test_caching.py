import unittest
from dataclasses import replace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from email_assistant.basic.application.services import EmailHistoryService, ProcessEmailService
from email_assistant.basic.application.usage import UsageLimits
from email_assistant.basic.domain.models import TriageClassification, TriageResult
from email_assistant.basic.infrastructure.classification_cache import InMemoryClassificationCache
from email_assistant.basic.infrastructure.usage_counter import InMemoryUsageCounter
from email_assistant.basic.interfaces.http.app import create_app
from tests.basic.fakes import TEST_USER, InMemoryEmailProcessingRepository
from tests.basic.test_services import RecordingResponder, make_email


RESULT = TriageResult(TriageClassification.RESPOND, "Reply requested")


class ClassificationCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_keys_include_user_and_every_email_field(self):
        cache = InMemoryClassificationCache()
        email = make_email(1)
        await cache.set(TEST_USER.id, email, RESULT)
        self.assertEqual(await cache.get(TEST_USER.id, email), RESULT)
        self.assertIsNone(await cache.get(uuid4(), email))
        for field in ("author", "recipient", "subject", "thread"):
            changed = replace(email, **{field: getattr(email, field) + "changed"})
            self.assertIsNone(await cache.get(TEST_USER.id, changed))

    async def test_ttl_is_not_extended_by_hits(self):
        now = [0.0]
        cache = InMemoryClassificationCache(ttl_seconds=10, clock=lambda: now[0])
        email = make_email(1)
        await cache.set(TEST_USER.id, email, RESULT)
        now[0] = 9
        self.assertEqual(await cache.get(TEST_USER.id, email), RESULT)
        now[0] = 10
        self.assertIsNone(await cache.get(TEST_USER.id, email))

    async def test_capacity_evicts_least_recently_used(self):
        cache = InMemoryClassificationCache(max_entries=2)
        first, second, third = (make_email(i) for i in range(3))
        await cache.set(TEST_USER.id, first, RESULT)
        await cache.set(TEST_USER.id, second, RESULT)
        await cache.get(TEST_USER.id, first)
        await cache.set(TEST_USER.id, third, RESULT)
        self.assertIsNone(await cache.get(TEST_USER.id, second))
        self.assertEqual(await cache.get(TEST_USER.id, first), RESULT)
        self.assertEqual(await cache.get(TEST_USER.id, third), RESULT)

    async def test_expired_entries_removed_before_live_lru_entry(self):
        now = [0.0]
        cache = InMemoryClassificationCache(10, 2, lambda: now[0])
        await cache.set(TEST_USER.id, make_email(1), RESULT)
        now[0] = 5
        await cache.set(TEST_USER.id, make_email(2), RESULT)
        await cache.get(TEST_USER.id, make_email(1))
        now[0] = 10
        await cache.set(TEST_USER.id, make_email(3), RESULT)
        self.assertEqual(await cache.get(TEST_USER.id, make_email(2)), RESULT)

    async def test_failed_classification_is_not_cached(self):
        classifier = AsyncMock()
        classifier.classify.side_effect = [RuntimeError("provider failed"), RESULT]
        service = ProcessEmailService(
            classifier, RecordingResponder(), InMemoryEmailProcessingRepository(),
            classification_cache=InMemoryClassificationCache(),
        )
        with self.assertRaises(RuntimeError):
            await service.process(make_email(1), TEST_USER)
        await service.process(make_email(1), TEST_USER)
        await service.process(make_email(1), TEST_USER)
        self.assertEqual(classifier.classify.await_count, 2)

    async def test_disabled_cache_keeps_original_behavior(self):
        classifier = AsyncMock()
        classifier.classify.return_value = RESULT
        service = ProcessEmailService(
            classifier, RecordingResponder(), InMemoryEmailProcessingRepository(),
        )
        await service.process(make_email(1), TEST_USER)
        await service.process(make_email(1), TEST_USER)
        self.assertEqual(classifier.classify.await_count, 2)

    def test_invalid_cache_configuration(self):
        for options in ({"ttl_seconds": 0}, {"max_entries": 0}):
            with self.assertRaises(ValueError):
                InMemoryClassificationCache(**options)


class CacheHttpTests(unittest.TestCase):
    def test_single_batch_stream_share_cache_without_skipping_history_or_quota(self):
        classifier = AsyncMock()
        classifier.classify.return_value = RESULT
        responder = RecordingResponder()
        repository = InMemoryEmailProcessingRepository()
        auth = AsyncMock()
        auth.current_user.return_value = TEST_USER
        app = create_app(
            ProcessEmailService(classifier, responder, repository,
                                classification_cache=InMemoryClassificationCache()),
            EmailHistoryService(repository), auth,
            UsageLimits(InMemoryUsageCounter(), emails_per_minute=4),
        )
        body = {"author": "sender@example.com", "to": "recipient@example.com",
                "subject": "Test", "email_thread": "Please reply"}
        headers = {"Authorization": "Bearer user"}
        with TestClient(app) as client:
            self.assertEqual(client.post("/emails/process", json=body, headers=headers).status_code, 200)
            self.assertEqual(client.post("/emails/process/batch", json={"emails": [body, body]},
                                         headers=headers).status_code, 200)
            stream = client.post("/emails/process/stream", json=body, headers=headers)
            self.assertEqual(stream.status_code, 200)
            self.assertIn("event: completed", stream.text)
            self.assertEqual(classifier.classify.await_count, 1)
            self.assertEqual(len(responder.responded_to), 4)
            self.assertEqual(len(repository.records), 4)
            self.assertEqual(client.post("/emails/process", json=body, headers=headers).status_code, 429)
            auth.current_user.return_value = replace(TEST_USER, id=uuid4())
            self.assertEqual(client.post("/emails/process", json=body, headers=headers).status_code, 200)
            self.assertEqual(classifier.classify.await_count, 2)
