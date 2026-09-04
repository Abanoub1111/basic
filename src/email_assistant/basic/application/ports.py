from typing import Protocol
from abc import abstractmethod
from email_assistant.basic.domain.models import Email, TriageResult


class EmailClassifier(Protocol):
    """Contract for anything capable of classifying an email."""

    @abstractmethod
    def classify(self, email: Email) -> TriageResult:
        """Classify an email."""
        ...


class EmailResponder(Protocol):
    """Contract for anything capable of responding to an email."""
    
    @abstractmethod
    def respond(self, email: Email) -> None:
        """Perform the actions required to respond to an email."""
        ...