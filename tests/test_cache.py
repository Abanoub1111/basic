"""Cache boundaries: exact keys, expiration, and least-recently-used eviction."""
from dataclasses import replace
from uuid import uuid4

import pytest

from email_assistant.basic.infrastructure.classification_cache import InMemoryClassificationCache


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
