import math
import time
from collections.abc import Callable
from threading import Lock

from email_assistant.basic.application.usage import UsageCharge, RateLimitExceeded


class InMemoryUsageCounter:
    """Rolling 60-second window, shared within one server process only."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._events: dict[str, list[tuple[float, int]]] = {}
        self._lock = Lock()

    def consume(self, charges: list[UsageCharge]) -> None:
        if len({charge.key for charge in charges}) != len(charges):
            raise ValueError("Charge keys must be distinct")
        if any(c.amount < 1 or c.limit < 1 for c in charges):
            raise ValueError("Charges and limits must be positive")
        with self._lock:
            now = self._clock()
            # Remove expired entries, including inactive users/IPs.
            self._events = {
                key: recent for key, events in self._events.items()
                if (recent := [(t, n) for t, n in events if t > now - 60])
            }
            wait = 0
            for charge in charges:
                events = self._events.get(charge.key, [])
                excess = sum(n for _, n in events) + charge.amount - charge.limit
                if charge.amount > charge.limit:
                    # This batch must be reduced; time alone cannot admit it.
                    raise ValueError("Batch exceeds the configured per-minute capacity")
                for timestamp, amount in events:
                    if excess <= 0:
                        break
                    excess -= amount
                    wait = max(wait, math.ceil(timestamp + 60 - now))
            if wait:
                raise RateLimitExceeded(max(1, wait))
            for charge in charges:
                self._events.setdefault(charge.key, []).append((now, charge.amount))
