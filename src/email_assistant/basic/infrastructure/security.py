import asyncio
from uuid import UUID
from datetime import timezone, datetime

import jwt
from pwdlib import PasswordHash

from email_assistant.basic.application.auth import AuthenticationError, Session


class ArgonPasswordHasher:
    def __init__(self):
        self._hasher = PasswordHash.recommended()

    async def hash(self, password: str) -> str:
        return await asyncio.to_thread(self._hasher.hash, password)

    async def verify(self, password: str, password_hash: str) -> bool:
        return await asyncio.to_thread(self._hasher.verify, password, password_hash)


class JwtTokenCodec:
    def __init__(self, secret: str):
        self._secret = secret
        self._issuer = "email-assistant"
        self._audience = "email-assistant-api"

    def encode(self, session: Session) -> str:
        return jwt.encode({
            "sub": str(session.user_id), "jti": str(session.id),
            "exp": session.expires_at, "iat": datetime.now(timezone.utc),
            "iss": self._issuer, "aud": self._audience,
        }, self._secret, algorithm="HS256")

    def decode(self, token: str) -> Session:
        try:
            data = jwt.decode(token, self._secret, algorithms=["HS256"],
                              issuer=self._issuer, audience=self._audience,
                              options={"require": ["sub", "jti", "exp", "iat", "iss", "aud"]})
            return Session(UUID(data["jti"]), UUID(data["sub"]),
                           datetime.fromtimestamp(data["exp"], UTC))
        except (jwt.InvalidTokenError, ValueError, TypeError, OverflowError) as error:
            raise AuthenticationError() from error
