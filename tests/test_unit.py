"""Isolated rules and services. No database or live AI calls."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
import asyncio

from pydantic import ValidationError
import pytest

from email_assistant.basic.application.auth import AuthenticationError, Session
from email_assistant.basic.application.models import ProcessingAction, ProcessingStatus
from email_assistant.basic.application.services import ProcessEmailService
from email_assistant.basic.application.usage import RateLimitExceeded, UsageCharge, UsageLimits
from email_assistant.basic.domain.models import TriageClassification, TriageResult
from email_assistant.basic.infrastructure import groq_classifier
from email_assistant.basic.infrastructure.classification_cache import InMemoryClassificationCache
from email_assistant.basic.infrastructure.security import JwtTokenCodec
from email_assistant.basic.infrastructure.usage_counter import InMemoryUsageCounter
from email_assistant.basic.interfaces.http.auth import RegisterRequest
from email_assistant.basic.interfaces.http.schemas import ProcessEmailRequest
from email_assistant.tools.default.calendar_tools import schedule_meeting

# Processing service


@pytest.mark.parametrize('classification,action', [
    (TriageClassification.RESPOND, ProcessingAction.RESPONDED),
    (TriageClassification.NOTIFY, ProcessingAction.NOTIFICATION_REQUIRED),
    (TriageClassification.IGNORE, ProcessingAction.IGNORED),
])
async def test_processing_decisions(service, classifier, responder, repository, email, user,
                                    classification, action):
    classifier.classify.return_value = TriageResult(classification, 'Test decision')
    result = await service.process(email, user)
    assert result.action == action
    assert repository.records[result.record_id].status == ProcessingStatus.COMPLETED
    if classification == TriageClassification.RESPOND:
        responder.respond.assert_awaited_once_with(email)
        assert result.reply.recipient == email.author
    else:
        responder.respond.assert_not_awaited()
        assert result.reply is None

async def test_cache_reuses_classification_but_creates_new_reply_and_history(
        service, classifier, responder, repository, email, user):
    first = await service.process(email, user)
    second = await service.process(email, user)
    classifier.classify.assert_awaited_once_with(email)
    assert responder.respond.await_count == 2
    assert first.record_id != second.record_id
    assert len(repository.records) == 2

async def test_provider_failure_is_saved_and_not_cached(service, classifier, repository, email, user):
    classifier.classify.side_effect = [RuntimeError('Provider failure'),
                                      TriageResult(TriageClassification.IGNORE, 'No reply')]
    with pytest.raises(RuntimeError, match='Provider failure'):
        await service.process(email, user)
    failed = next(iter(repository.records.values()))
    assert failed.status == ProcessingStatus.FAILED
    assert failed.failure_message == 'Email processing failed.'
    await service.process(email, user)
    assert classifier.classify.await_count == 2

async def test_closing_stream_marks_record_failed(service, repository, email, user):
    stream = service.process_stream(email, user)
    started = await anext(stream)
    await stream.aclose()
    assert repository.records[started.record_id].status == ProcessingStatus.FAILED
    assert repository.records[started.record_id].failure_message == 'Email processing was interrupted.'

async def test_batch_limits_concurrency_and_preserves_order(classifier, responder, repository, email, user):
    active = 0
    peak = 0
    two_started = asyncio.Event()
    release = asyncio.Event()

    async def classify(item):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if active == 2:
            two_started.set()
        try:
            await release.wait()
            return TriageResult(TriageClassification.IGNORE, item.subject)
        finally:
            active -= 1

    classifier.classify.side_effect = classify
    service = ProcessEmailService(classifier, responder, repository, max_concurrency=2)
    emails = [replace(email, subject=str(i)) for i in range(5)]
    task = asyncio.create_task(service.process_many(emails, user))
    try:
        await asyncio.wait_for(two_started.wait(), timeout=2)
    finally:
        release.set()
        results = await asyncio.wait_for(task, timeout=2)
    assert peak == 2
    assert [r.triage.reasoning for r in results] == [e.subject for e in emails]

# Classification cache


@pytest.mark.parametrize('field', ['author', 'recipient', 'subject', 'thread', 'user'])
async def test_cache_keys_include_user_and_all_email_fields(email, user, classifier, field):
    cache = InMemoryClassificationCache()
    result = classifier.classify.return_value
    await cache.set(user.id, email, result)
    assert await cache.get(user.id, email) == result
    changed = replace(email, **{field: 'different'}) if field != 'user' else email
    assert await cache.get(uuid4() if field == 'user' else user.id, changed) is None

async def test_reading_does_not_extend_expiration(email, user, classifier, now):
    cache = InMemoryClassificationCache(ttl_seconds=10, clock=lambda: now[0])
    await cache.set(user.id, email, classifier.classify.return_value)
    now[0] = 9
    assert await cache.get(user.id, email) is not None
    now[0] = 10
    assert await cache.get(user.id, email) is None

async def test_full_cache_evicts_least_recently_used(email, user, classifier):
    cache = InMemoryClassificationCache(max_entries=2)
    a, b, c = [replace(email, subject=s) for s in 'ABC']
    for item in (a, b):
        await cache.set(user.id, item, classifier.classify.return_value)
    await cache.get(user.id, a)
    await cache.set(user.id, c, classifier.classify.return_value)
    assert await cache.get(user.id, b) is None
    assert await cache.get(user.id, a) is not None
    assert await cache.get(user.id, c) is not None

@pytest.mark.parametrize('options', [{'ttl_seconds': 0}, {'max_entries': 0}])
def test_invalid_cache_settings(options):
    with pytest.raises(ValueError):
        InMemoryClassificationCache(**options)

# Input and token validation


@pytest.mark.parametrize('subject,valid', [('Hello', True), ('  Hello  ', True),
                                        ('', False), ('   ', False),
                                        ('x' * 500, True), ('x' * 501, False)])
def test_subject_validation(payload, subject, valid):
    payload['subject'] = subject
    if valid:
        assert ProcessEmailRequest(**payload).subject == subject.strip()
    else:
        with pytest.raises(ValidationError):
            ProcessEmailRequest(**payload)

@pytest.mark.parametrize('extra', [{'unexpected': True}, {'email_thread': 'x' * 10001}])
def test_rejects_extra_fields_and_oversized_thread(payload, extra):
    with pytest.raises(ValidationError):
        ProcessEmailRequest(**(payload | extra))

def test_password_preserved_and_role_cannot_be_chosen():
    credentials = dict(email='a@example.com', password='  a long password  ')
    assert RegisterRequest(**credentials).password == credentials['password']
    with pytest.raises(ValidationError):
        RegisterRequest(**credentials, role='ADMIN')

@pytest.mark.parametrize('expired,wrong_key', [(False, False), (True, False), (False, True)])
def test_token_validation(expired, wrong_key):
    codec = JwtTokenCodec('a' * 48)
    session = Session(uuid4(), uuid4(), datetime.now(timezone.utc) +
                      timedelta(minutes=-5 if expired else 5))
    token = JwtTokenCodec(('b' if wrong_key else 'a') * 48).encode(session)
    if expired or wrong_key:
        with pytest.raises(AuthenticationError):
            codec.decode(token)
    else:
        assert codec.decode(token).user_id == session.user_id

def test_calendar_accepts_iso_date():
    result = schedule_meeting.invoke(dict(attendees=['manager@example.com'], subject='Project',
                                          duration_minutes=30, preferred_day='2026-09-06', start_time=14))
    assert 'September 06, 2026' in result

# Rate limits


def test_weighted_quota_expires(now):
    counter = InMemoryUsageCounter(lambda: now[0])
    counter.consume([UsageCharge('user', 3, 3)])
    now[0] = 20
    with pytest.raises(RateLimitExceeded) as error:
        counter.consume([UsageCharge('user', 3)])
    assert error.value.retry_after == 40
    now[0] = 60
    counter.consume([UsageCharge('user', 3, 3)])

def test_concurrent_requests_cannot_exceed_quota():
    counter = InMemoryUsageCounter(lambda: 0)

    def attempt(_):
        try:
            counter.consume([UsageCharge('user', 5)])
            return True
        except RateLimitExceeded:
            return False

    with ThreadPoolExecutor(max_workers=10) as pool:
        assert sum(pool.map(attempt, range(30))) == 5

def test_rejected_login_does_not_spend_other_ip_quota():
    usage = UsageLimits(InMemoryUsageCounter(lambda: 0), login_ip_per_minute=1,
                        login_email_per_minute=1)
    usage.login('ip-a', ' FIRST@example.com ')
    with pytest.raises(RateLimitExceeded):
        usage.login('ip-b', 'first@example.com')
    usage.login('ip-b', 'second@example.com')
    with pytest.raises(RateLimitExceeded):
        usage.login('ip-b', 'third@example.com')

# AI adapters and graph


@pytest.mark.parametrize('output,valid', [
    ({'classification': 'respond', 'reasoning': 'Direct question'}, True),
    ({'classification': 'invalid', 'reasoning': 'Direct question'}, False),
    ({'classification': 'respond', 'reasoning': ' '}, False),
])
async def test_classifier_validates_provider_output(monkeypatch, email, output, valid):
    router = AsyncMock()
    router.ainvoke.return_value = output
    model = Mock()
    model.with_structured_output.return_value = router
    monkeypatch.setattr(groq_classifier, 'init_chat_model', Mock(return_value=model))
    classifier = groq_classifier.GroqEmailClassifier(api_key='test')
    if valid:
        result = await classifier.classify(email)
        assert result.classification.value == 'respond'
        assert result.reasoning == 'Direct question'
        messages = router.ainvoke.call_args.args[0]
        assert email.thread in messages[1]['content']
    else:
        with pytest.raises(ValidationError):
            await classifier.classify(email)
