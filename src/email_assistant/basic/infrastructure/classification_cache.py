import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from hashlib import sha256
import json
from uuid import UUID

from email_assistant.basic.domain.models import Email, TriageResult


logger = logging.getLogger(__name__)


class InMemoryClassificationCache:
    """Exact-match TTL cache with LRU eviction, for one application event loop."""

    def __init__(
        self,
        ttl_seconds: int = 300,
        max_entries: int = 1000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds < 1 or max_entries < 1:
            raise ValueError("Cache TTL and capacity must be positive")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, tuple[float, TriageResult]] = OrderedDict()

    @staticmethod
    def _key(user_id: UUID, email: Email) -> str:
        # Structured encoding avoids ambiguous concatenation; no raw email in keys.
        payload = json.dumps(
            [str(user_id), email.author, email.recipient, email.subject, email.thread],
            ensure_ascii=False,
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    async def get(self, user_id: UUID, email: Email) -> TriageResult | None:
        key = self._key(user_id, email)
        entry = self._entries.get(key)
        if entry is not None:
            expires_at, result = entry
            if self._clock() < expires_at:
                self._entries.move_to_end(key)
                logger.info("Classification cache HIT")
                return result
            del self._entries[key]
        logger.info("Classification cache MISS")
        return None

    async def set(self, user_id: UUID, email: Email, result: TriageResult) -> None:
        now = self._clock()
        for key, (expires_at, _) in list(self._entries.items()):
            if expires_at <= now:
                del self._entries[key]
        key = self._key(user_id, email)
        self._entries[key] = (now + self._ttl_seconds, result)
        self._entries.move_to_end(key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
