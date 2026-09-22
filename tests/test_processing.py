"""Unit tests: real service logic with fake database and AI dependencies."""
import asyncio
from dataclasses import replace

import pytest

from email_assistant.basic.application.models import ProcessingAction, ProcessingStatus
from email_assistant.basic.application.services import ProcessEmailService
from email_assistant.basic.domain.models import TriageClassification, TriageResult


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
