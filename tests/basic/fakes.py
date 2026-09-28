from dataclasses import replace
from datetime import timezone, datetime
from uuid import UUID, uuid4

from email_assistant.basic.application.models import (
    EmailProcessingRecord,
    ProcessEmailResult,
    ProcessingStatus,
)
from email_assistant.basic.domain.models import Email
from email_assistant.basic.domain.users import User, UserRole

TEST_USER = User(uuid4(), "tester@example.com", UserRole.USER, True)

class FakeAuthService:
    async def current_user(self, token):
        return TEST_USER



class InMemoryEmailProcessingRepository:
    """Small repository fake used by application unit tests."""

    def __init__(self) -> None:
        self.records: dict[UUID, EmailProcessingRecord] = {}

    async def create(self, email: Email, owner_id: UUID) -> EmailProcessingRecord:
        now = datetime.now(timezone.utc)
        record = EmailProcessingRecord(
            id=uuid4(),
            owner_id=owner_id,
            email=email,
            status=ProcessingStatus.PROCESSING,
            result=None,
            failure_message=None,
            created_at=now,
            updated_at=now,
        )
        self.records[record.id] = record
        return record

    async def complete(
        self,
        record_id: UUID,
        result: ProcessEmailResult,
    ) -> EmailProcessingRecord:
        record = replace(
            self.records[record_id],
            status=ProcessingStatus.COMPLETED,
            result=result,
            updated_at=datetime.now(timezone.utc),
        )
        self.records[record_id] = record
        return record

    async def fail(
        self,
        record_id: UUID,
        failure_message: str,
    ) -> EmailProcessingRecord:
        record = replace(
            self.records[record_id],
            status=ProcessingStatus.FAILED,
            failure_message=failure_message,
            updated_at=datetime.now(timezone.utc),
        )
        self.records[record_id] = record
        return record

    async def get(self, record_id: UUID) -> EmailProcessingRecord | None:
        return self.records.get(record_id)

    async def list(
        self,
        skip: int,
        limit: int,
    ) -> list[EmailProcessingRecord]:
        records = sorted(
            self.records.values(),
            key=lambda record: record.created_at,
            reverse=True,
        )
        return records[skip : skip + limit]

    async def delete(self, record_id: UUID) -> bool:
        return self.records.pop(record_id, None) is not None
