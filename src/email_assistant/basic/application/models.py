from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID

from email_assistant.basic.domain.models import (
    Email,
    EmailReply,
    TriageResult,
)


class ProcessingAction(str, Enum):
    """Action taken after an email has been classified."""

    RESPONDED = "responded"
    NOTIFICATION_REQUIRED = "notification_required"
    IGNORED = "ignored"


class ProcessingStatus(str, Enum):
    """Persistence state of one email-processing operation."""

    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ProcessEmailResult:
    """Result returned after processing an email."""

    record_id: UUID
    triage: TriageResult
    action: ProcessingAction
    reply: EmailReply | None = None


@dataclass(frozen=True)
class EmailProcessingRecord:
    """Application representation of a stored processing operation."""

    id: UUID
    email: Email
    status: ProcessingStatus
    result: ProcessEmailResult | None
    failure_message: str | None
    created_at: datetime
    updated_at: datetime
    owner_id: UUID | None = None
