from pydantic import BaseModel, Field

from email_assistant.basic.application.services import (
    ProcessEmailResult,
    ProcessingAction,
)
from email_assistant.basic.domain.models import (
    Email,
    TriageClassification,
)


class ProcessEmailRequest(BaseModel):
    """JSON body accepted by the process-email endpoint."""

    author: str = Field(min_length=1)
    to: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    email_thread: str = Field(min_length=1)

    def to_domain(self) -> Email:
        """Convert the HTTP request into a domain Email."""

        return Email(
            author=self.author,
            recipient=self.to,
            subject=self.subject,
            thread=self.email_thread,
        )


class ProcessEmailResponse(BaseModel):
    """JSON returned after processing an email."""

    classification: TriageClassification
    reasoning: str
    action: ProcessingAction

    @classmethod
    def from_result(
        cls,
        result: ProcessEmailResult,
    ) -> "ProcessEmailResponse":
        """Convert an application result into an HTTP response."""

        return cls(
            classification=result.triage.classification,
            reasoning=result.triage.reasoning,
            action=result.action,
        )


class HealthResponse(BaseModel):
    """Response returned by the health endpoint."""

    status: str