"""One small database fake; production adapters are tested separately."""
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

from email_assistant.basic.application.models import EmailProcessingRecord, ProcessingStatus


class MemoryRepository:
    def __init__(self):
        self.records = {}

    async def create(self, email, owner_id):
        now = datetime.now(timezone.utc)
        record = EmailProcessingRecord(
            id=uuid4(), owner_id=owner_id, email=email,
            status=ProcessingStatus.PROCESSING, result=None, failure_message=None,
            created_at=now, updated_at=now,
        )
        self.records[record.id] = record
        return record

    async def complete(self, record_id, result):
        record = replace(self.records[record_id], status=ProcessingStatus.COMPLETED,
                         result=result, updated_at=datetime.now(timezone.utc))
        self.records[record_id] = record
        return record

    async def fail(self, record_id, failure_message):
        record = replace(self.records[record_id], status=ProcessingStatus.FAILED,
                         failure_message=failure_message, updated_at=datetime.now(timezone.utc))
        self.records[record_id] = record
        return record

    async def get(self, record_id, owner_id=None):
        record = self.records.get(record_id)
        if record and (owner_id is None or record.owner_id == owner_id):
            return record
        return None

    async def list(self, skip, limit, owner_id=None):
        records = [r for r in self.records.values()
                   if owner_id is None or r.owner_id == owner_id]
        records.sort(key=lambda r: r.created_at, reverse=True)
        return records[skip:skip + limit]

    async def delete(self, record_id, owner_id=None):
        if await self.get(record_id, owner_id) is None:
            return False
        del self.records[record_id]
        return True
