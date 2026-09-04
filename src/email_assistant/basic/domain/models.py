from dataclasses import dataclass
from enum import Enum


class TriageClassification(str, Enum):
    """Possible decisions when an email is classified."""

    RESPOND = "respond"
    NOTIFY = "notify"
    IGNORE = "ignore"


@dataclass(frozen=True)
class Email:
    """An email understood by the business logic."""

    author: str
    recipient: str
    subject: str
    thread: str


@dataclass(frozen=True)
class TriageResult:
    """The result produced by classifying an email."""

    classification: TriageClassification
    reasoning: str