from datetime import timezone, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from email_assistant.basic.application.auth import AccountExistsError, Session, UserCredentials
from email_assistant.basic.domain.users import User, UserRole
from email_assistant.basic.infrastructure.database.models import UserRow, SessionRow


class SqlAlchemyAuthRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self._sessions = sessions

    @staticmethod
    def _user(row: UserRow) -> User:
        return User(row.id, row.email, UserRole(row.role), row.is_active)

    async def find_user(self, email: str) -> UserCredentials | None:
        async with self._sessions() as db:
            row = await db.scalar(select(UserRow).where(UserRow.email == email))
            return UserCredentials(self._user(row), row.password_hash) if row else None

    async def create_user(self, email: str, password_hash: str, role: UserRole) -> User:
        row = UserRow(id=uuid4(), email=email, password_hash=password_hash,
                      role=role.value, is_active=True, created_at=datetime.now(timezone.utc))
        try:
            async with self._sessions.begin() as db:
                db.add(row)
        except IntegrityError as error:
            raise AccountExistsError() from error
        return self._user(row)

    async def create_session(self, session: Session) -> None:
        async with self._sessions.begin() as db:
            db.add(SessionRow(id=session.id, user_id=session.user_id,
                              expires_at=session.expires_at, created_at=datetime.now(timezone.utc)))

    async def get_session_user(self, session: Session) -> User | None:
        statement = select(UserRow).join(SessionRow, SessionRow.user_id == UserRow.id).where(
            SessionRow.id == session.id, SessionRow.user_id == session.user_id,
            SessionRow.revoked_at.is_(None), SessionRow.expires_at > datetime.now(timezone.utc),
        )
        async with self._sessions() as db:
            row = await db.scalar(statement)
            return self._user(row) if row else None

    async def revoke_session(self, session_id: UUID) -> None:
        async with self._sessions.begin() as db:
            await db.execute(update(SessionRow).where(SessionRow.id == session_id)
                             .values(revoked_at=datetime.now(timezone.utc)))
