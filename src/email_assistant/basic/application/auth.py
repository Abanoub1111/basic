from dataclasses import dataclass
from datetime import timezone, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from email_assistant.basic.domain.users import User, UserRole


class AuthenticationError(Exception):
    pass


class AccountExistsError(Exception):
    pass


@dataclass(frozen=True)
class UserCredentials:
    user: User
    password_hash: str


@dataclass(frozen=True)
class Session:
    id: UUID
    user_id: UUID
    expires_at: datetime


class AuthRepository(Protocol):
    async def find_user(self, email: str) -> UserCredentials | None: ...
    async def create_user(self, email: str, password_hash: str, role: UserRole) -> User: ...
    async def create_session(self, session: Session) -> None: ...
    async def get_session_user(self, session: Session) -> User | None: ...
    async def revoke_session(self, session_id: UUID) -> None: ...


class PasswordHasher(Protocol):
    async def hash(self, password: str) -> str: ...
    async def verify(self, password: str, password_hash: str) -> bool: ...


class TokenCodec(Protocol):
    def encode(self, session: Session) -> str: ...
    def decode(self, token: str) -> Session: ...


class AuthService:
    def __init__(self, repository: AuthRepository, passwords: PasswordHasher,
                 tokens: TokenCodec, lifetime_minutes: int = 30):
        self.repository = repository
        self.passwords = passwords
        self.tokens = tokens
        self.lifetime_minutes = lifetime_minutes

    async def register(self, email: str, password: str) -> User:
        email = email.strip().lower()
        if await self.repository.find_user(email):
            raise AccountExistsError()
        return await self.repository.create_user(
            email, await self.passwords.hash(password), UserRole.USER,
        )

    async def login(self, email: str, password: str) -> str:
        credentials = await self.repository.find_user(email.strip().lower())
        if credentials is None:
            # Perform expensive password work for unknown accounts too.
            await self.passwords.hash(password)
            raise AuthenticationError()
        valid = await self.passwords.verify(password, credentials.password_hash)
        if not valid or not credentials.user.is_active:
            raise AuthenticationError()
        session = Session(uuid4(), credentials.user.id,
                          datetime.now(timezone.utc) + timedelta(minutes=self.lifetime_minutes))
        await self.repository.create_session(session)
        return self.tokens.encode(session)

    async def current_user(self, token: str) -> User:
        session = self.tokens.decode(token)
        user = await self.repository.get_session_user(session)
        if user is None or not user.is_active:
            raise AuthenticationError()
        return user

    async def logout(self, token: str) -> None:
        await self.current_user(token)
        await self.repository.revoke_session(self.tokens.decode(token).id)
