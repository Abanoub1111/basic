"""Rate-limit policy with a controlled clock and concurrent requests."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from email_assistant.basic.application.usage import RateLimitExceeded, UsageCharge, UsageLimits
from email_assistant.basic.infrastructure.usage_counter import InMemoryUsageCounter


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
