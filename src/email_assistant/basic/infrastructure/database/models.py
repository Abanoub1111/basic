from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for SQLAlchemy database models."""


class EmailProcessingRecordRow(Base):
    """Database row containing one email-processing operation."""

    __tablename__ = "email_processing_records"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    status: Mapped[str] = mapped_column(String(20), index=True)

    author: Mapped[str] = mapped_column(String(320))
    recipient: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(500))
    email_thread: Mapped[str] = mapped_column(Text)

    classification: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str | None] = mapped_column(String(30), nullable=True)

    reply_recipient: Mapped[str | None] = mapped_column(
        String(320),
        nullable=True,
    )
    reply_subject: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    reply_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
