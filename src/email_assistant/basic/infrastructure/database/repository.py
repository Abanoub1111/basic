from datetime import timezone, datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_assistant.basic.application.models import (
    EmailProcessingRecord,
    ProcessEmailResult,
    ProcessingAction,
    ProcessingStatus,
)
from email_assistant.basic.application.ports import EmailProcessingRepository
from email_assistant.basic.domain.models import (
    Email,
    EmailReply,
    TriageClassification,
    TriageResult,
)
from email_assistant.basic.infrastructure.database.models import (
    EmailProcessingRecordRow,
)


class SqlAlchemyEmailProcessingRepository(EmailProcessingRepository):
    """Store processing history with one session per operation."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
    ) -> None:
        self._sessions = sessions

    async def create(self, email: Email, owner_id: UUID) -> EmailProcessingRecord:
        now = datetime.now(timezone.utc)
        row = EmailProcessingRecordRow(
            id=uuid4(),
            owner_id=owner_id,
            status=ProcessingStatus.PROCESSING.value,
            author=email.author,
            recipient=email.recipient,
            subject=email.subject,
            email_thread=email.thread,
            created_at=now,
            updated_at=now,
        )

        async with self._sessions.begin() as session:
            session.add(row)

        return self._to_application(row)

    async def complete(
        self,
        record_id: UUID,
        result: ProcessEmailResult,
    ) -> EmailProcessingRecord:
        async with self._sessions.begin() as session:
            row = await self._require_row(session, record_id)
            row.status = ProcessingStatus.COMPLETED.value
            row.classification = result.triage.classification.value
            row.reasoning = result.triage.reasoning
            row.action = result.action.value
            row.failure_message = None
            row.updated_at = datetime.now(timezone.utc)

            if result.reply is not None:
                row.reply_recipient = result.reply.recipient
                row.reply_subject = result.reply.subject
                row.reply_content = result.reply.content

        return self._to_application(row)

    async def fail(
        self,
        record_id: UUID,
        failure_message: str,
    ) -> EmailProcessingRecord:
        async with self._sessions.begin() as session:
            row = await self._require_row(session, record_id)
            row.status = ProcessingStatus.FAILED.value
            row.failure_message = failure_message
            row.updated_at = datetime.now(timezone.utc)

        return self._to_application(row)

    async def get(self, record_id: UUID, owner_id: UUID | None = None) -> EmailProcessingRecord | None:
        async with self._sessions() as session:
            statement = select(EmailProcessingRecordRow).where(EmailProcessingRecordRow.id == record_id)
            if owner_id is not None:
                statement = statement.where(EmailProcessingRecordRow.owner_id == owner_id)
            row = await session.scalar(statement)
            return None if row is None else self._to_application(row)

    async def list(
        self,
        skip: int,
        limit: int,
        owner_id: UUID | None = None,
    ) -> list[EmailProcessingRecord]:
        statement = (
            select(EmailProcessingRecordRow)
            .order_by(EmailProcessingRecordRow.created_at.desc())
            .offset(skip)
            .limit(limit)
        )

        if owner_id is not None:
            statement = statement.where(EmailProcessingRecordRow.owner_id == owner_id)
        async with self._sessions() as session:
            rows = (await session.scalars(statement)).all()
            return [self._to_application(row) for row in rows]

    async def delete(self, record_id: UUID, owner_id: UUID | None = None) -> bool:
        statement = delete(EmailProcessingRecordRow).where(
            EmailProcessingRecordRow.id == record_id
        )

        if owner_id is not None:
            statement = statement.where(EmailProcessingRecordRow.owner_id == owner_id)
        async with self._sessions.begin() as session:
            result = await session.execute(statement)

        return result.rowcount > 0

    @staticmethod
    async def _require_row(
        session: AsyncSession,
        record_id: UUID,
    ) -> EmailProcessingRecordRow:
        row = await session.get(EmailProcessingRecordRow, record_id)
        if row is None:
            raise LookupError(f"Processing record {record_id} was not found")
        return row

    @staticmethod
    def _to_application(
        row: EmailProcessingRecordRow,
    ) -> EmailProcessingRecord:
        email = Email(
            author=row.author,
            recipient=row.recipient,
            subject=row.subject,
            thread=row.email_thread,
        )
        result = None

        if row.status == ProcessingStatus.COMPLETED.value:
            if row.classification is None or row.reasoning is None:
                raise ValueError("Completed record has incomplete triage data")
            if row.action is None:
                raise ValueError("Completed record has no action")

            reply = None
            if row.reply_content is not None:
                if row.reply_recipient is None or row.reply_subject is None:
                    raise ValueError("Stored reply is incomplete")
                reply = EmailReply(
                    recipient=row.reply_recipient,
                    subject=row.reply_subject,
                    content=row.reply_content,
                )

            result = ProcessEmailResult(
                record_id=row.id,
                triage=TriageResult(
                    classification=TriageClassification(row.classification),
                    reasoning=row.reasoning,
                ),
                action=ProcessingAction(row.action),
                reply=reply,
            )

        return EmailProcessingRecord(
            id=row.id,
            owner_id=row.owner_id,
            email=email,
            status=ProcessingStatus(row.status),
            result=result,
            failure_message=row.failure_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
