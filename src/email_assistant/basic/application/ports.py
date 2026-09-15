from abc import abstractmethod
from typing import Protocol
from uuid import UUID

from email_assistant.basic.application.models import (
    EmailProcessingRecord,
    ProcessEmailResult,
)
from email_assistant.basic.domain.models import Email, EmailReply, TriageResult


class EmailClassifier(Protocol):
    """Contract for anything capable of classifying an email."""

    @abstractmethod
    async def classify(self, email: Email) -> TriageResult:
        """Classify an email."""
        ...


class ClassificationCache(Protocol):
    """Temporary classification storage, isolated by the requesting user."""

    async def get(self, user_id: UUID, email: Email) -> TriageResult | None:
        ...

    async def set(self, user_id: UUID, email: Email, result: TriageResult) -> None:
        ...


class EmailResponder(Protocol):
    """Contract for anything capable of responding to an email."""

    @abstractmethod
    async def respond(self, email: Email) -> EmailReply:
        """Perform the actions required to respond to an email."""
        ...


class EmailProcessingRepository(Protocol):
    """Persistence contract required by the application layer."""

    @abstractmethod
    async def create(self, email: Email, owner_id: UUID) -> EmailProcessingRecord:
        """Store a new processing operation."""
        ...

    @abstractmethod
    async def complete(
        self,
        record_id: UUID,
        result: ProcessEmailResult,
    ) -> EmailProcessingRecord:
        """Store the successful result of an operation."""
        ...

    @abstractmethod
    async def fail(
        self,
        record_id: UUID,
        failure_message: str,
    ) -> EmailProcessingRecord:
        """Mark an operation as failed."""
        ...

    @abstractmethod
    async def get(self, record_id: UUID, owner_id: UUID | None = None) -> EmailProcessingRecord | None:
        """Return one stored operation, if it exists."""
        ...

    @abstractmethod
    async def list(
        self,
        skip: int,
        limit: int,
        owner_id: UUID | None = None,
    ) -> list[EmailProcessingRecord]:
        """Return stored operations newest first."""
        ...

    @abstractmethod
    async def delete(self, record_id: UUID, owner_id: UUID | None = None) -> bool:
        """Delete one operation and report whether it existed."""
        ...
