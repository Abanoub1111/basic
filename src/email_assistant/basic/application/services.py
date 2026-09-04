from dataclasses import dataclass
from enum import Enum

from email_assistant.basic.application.ports import (
    EmailClassifier,
    EmailResponder,
)
from email_assistant.basic.domain.models import (
    Email,
    TriageClassification,
    TriageResult,
)


class ProcessingAction(str, Enum):
    """Action taken after an email has been classified."""

    RESPONDED = "responded"
    NOTIFICATION_REQUIRED = "notification_required"
    IGNORED = "ignored"


@dataclass(frozen=True)
class ProcessEmailResult:
    """Result returned after processing an email."""

    triage: TriageResult
    action: ProcessingAction


class ProcessEmailService:
    """Coordinate email classification and response."""

    def __init__(
        self,
        classifier: EmailClassifier,
        responder: EmailResponder,
    ) -> None:
        self._classifier = classifier
        self._responder = responder

    def process(self, email: Email) -> ProcessEmailResult:
        """Classify an email and perform the appropriate action."""

        triage_result = self._classifier.classify(email)

        if triage_result.classification is TriageClassification.RESPOND:
            self._responder.respond(email)
            action = ProcessingAction.RESPONDED

        elif triage_result.classification is TriageClassification.NOTIFY:
            action = ProcessingAction.NOTIFICATION_REQUIRED

        elif triage_result.classification is TriageClassification.IGNORE:
            action = ProcessingAction.IGNORED

        else:
            raise ValueError(
                f"Unsupported classification: {triage_result.classification}"
            )

        return ProcessEmailResult(
            triage=triage_result,
            action=action,
        )