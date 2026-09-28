from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__("Rate limit exceeded")


@dataclass(frozen=True)
class UsageCharge:
    key: str
    limit: int
    amount: int = 1


class UsageCounter(Protocol):
    def consume(self, charges: list[UsageCharge]) -> None:
        """Atomically accept all charges or raise RateLimitExceeded."""
        ...


class UsageLimits:
    """Small usage policy shared by the HTTP entry points."""

    def __init__(self, counter: UsageCounter, emails_per_minute: int = 20,
                 login_ip_per_minute: int = 10, login_email_per_minute: int = 5):
        if min(emails_per_minute, login_ip_per_minute, login_email_per_minute) < 1:
            raise ValueError("Usage limits must be positive")
        self.counter = counter
        self.emails_per_minute = emails_per_minute
        self.login_ip_per_minute = login_ip_per_minute
        self.login_email_per_minute = login_email_per_minute

    def process(self, user_id: UUID, count: int = 1) -> None:
        self.counter.consume([UsageCharge(f"emails:{user_id}", self.emails_per_minute, count)])

    def login(self, ip: str, email: str) -> None:
        self.counter.consume([
            UsageCharge(f"login-ip:{ip}", self.login_ip_per_minute),
            UsageCharge(f"login-email:{email.strip().lower()}", self.login_email_per_minute),
        ])
