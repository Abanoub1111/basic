from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from email_assistant.basic.application.services import (
    ProcessEmailResult,
    ProcessingAction,
)
from email_assistant.basic.domain.models import (
    Email,
    TriageClassification,
)


class ApiModel(BaseModel):
    """Base model for strict validation at the HTTP boundary."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


class ProcessEmailRequest(ApiModel):
    """JSON body accepted by the process-email endpoint."""

    author: str = Field(min_length=1, max_length=320)
    to: str = Field(min_length=1, max_length=320)
    subject: str = Field(min_length=1, max_length=500)
    email_thread: str = Field(min_length=1, max_length=10_000)

    def to_domain(self) -> Email:
        """Convert the HTTP request into a domain Email."""

        return Email(
            author=self.author,
            recipient=self.to,
            subject=self.subject,
            thread=self.email_thread,
        )


class ProcessEmailResponse(ApiModel):
    """JSON returned after processing an email."""

    classification: TriageClassification
    reasoning: str = Field(min_length=1, max_length=2_000)
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


class HealthResponse(ApiModel):
    """Response returned by the health endpoint."""

    status: Literal["ok"]
