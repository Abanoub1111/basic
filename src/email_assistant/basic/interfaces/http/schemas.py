from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from email_assistant.basic.application.models import (
    EmailProcessingRecord,
    ProcessEmailResult,
    ProcessingAction,
    ProcessingStatus,
)
from email_assistant.basic.domain.models import (
    Email,
    EmailReply,
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


class EmailReplyResponse(ApiModel):
    """Reply drafted by the response workflow."""

    recipient: str
    subject: str
    content: str

    @classmethod
    def from_domain(cls, reply: EmailReply) -> "EmailReplyResponse":
        """Convert a domain reply into its HTTP representation."""

        return cls(
            recipient=reply.recipient,
            subject=reply.subject,
            content=reply.content,
        )


class StreamStartedData(ApiModel):
    """Payload sent when email processing starts."""

    stage: Literal["started"] = "started"
    record_id: UUID


class StreamClassifiedData(ApiModel):
    """Payload sent after email classification."""

    classification: TriageClassification
    reasoning: str = Field(min_length=1, max_length=2_000)


class StreamRespondingData(ApiModel):
    """Payload sent before running the response workflow."""

    stage: Literal["responding"] = "responding"


class StreamCompletedData(ApiModel):
    """Payload sent when email processing completes."""

    action: ProcessingAction
    record_id: UUID


class StreamErrorData(ApiModel):
    """Safe error payload sent after an SSE stream has started."""

    message: str = Field(min_length=1)


class ProcessEmailResponse(ApiModel):
    """JSON returned after processing an email."""

    record_id: UUID
    classification: TriageClassification
    reasoning: str = Field(min_length=1, max_length=2_000)
    action: ProcessingAction
    reply: EmailReplyResponse | None

    @classmethod
    def from_result(
        cls,
        result: ProcessEmailResult,
    ) -> "ProcessEmailResponse":
        """Convert an application result into an HTTP response."""

        return cls(
            record_id=result.record_id,
            classification=result.triage.classification,
            reasoning=result.triage.reasoning,
            action=result.action,
            reply=(
                EmailReplyResponse.from_domain(result.reply)
                if result.reply is not None
                else None
            ),
        )


class ProcessEmailsBatchRequest(ApiModel):
    """JSON body accepted by the batch process-email endpoint."""

    emails: list[ProcessEmailRequest] = Field(min_length=1, max_length=20)

    def to_domain(self) -> list[Email]:
        """Convert all HTTP email requests into domain emails."""

        return [email.to_domain() for email in self.emails]


class ProcessEmailsBatchResponse(ApiModel):
    """JSON returned after processing a batch of emails."""

    results: list[ProcessEmailResponse]

    @classmethod
    def from_results(
        cls,
        results: list[ProcessEmailResult],
    ) -> "ProcessEmailsBatchResponse":
        """Convert application results into an HTTP batch response."""

        return cls(
            results=[
                ProcessEmailResponse.from_result(result)
                for result in results
            ]
        )


class EmailHistoryResponse(ApiModel):
    """Stored state and result of one processing operation."""

    id: UUID
    status: ProcessingStatus
    email: ProcessEmailRequest
    result: ProcessEmailResponse | None
    failure_message: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_record(
        cls,
        record: EmailProcessingRecord,
    ) -> "EmailHistoryResponse":
        return cls(
            id=record.id,
            status=record.status,
            email=ProcessEmailRequest(
                author=record.email.author,
                to=record.email.recipient,
                subject=record.email.subject,
                email_thread=record.email.thread,
            ),
            result=(
                ProcessEmailResponse.from_result(record.result)
                if record.result is not None
                else None
            ),
            failure_message=record.failure_message,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )


class EmailHistoryListResponse(ApiModel):
    """Paginated collection of stored processing operations."""

    items: list[EmailHistoryResponse]
    skip: int
    limit: int


class HealthResponse(ApiModel):
    """Response returned by the health endpoint."""

    status: Literal["ok"]
