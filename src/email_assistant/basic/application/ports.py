from abc import abstractmethod

from typing import Protocol

from email_assistant.basic.domain.models import Email, EmailReply, TriageResult


class EmailClassifier(Protocol):
    """Contract for anything capable of classifying an email."""

    @abstractmethod
    async def classify(self, email: Email) -> TriageResult:
        """Classify an email."""
        ...


class EmailResponder(Protocol):
    """Contract for anything capable of responding to an email."""

    @abstractmethod
    async def respond(self, email: Email) -> EmailReply:
        """Perform the actions required to respond to an email."""
        ...
