import os
import unittest
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from email_assistant.basic.application.auth import AuthenticationError, Session
from email_assistant.basic.infrastructure.security import JwtTokenCodec
from email_assistant.basic.interfaces.http.auth import RegisterRequest
from pydantic import ValidationError


class TokenTests(unittest.TestCase):
    def test_expired_and_wrongly_signed_tokens_are_rejected(self):
        codec = JwtTokenCodec("a" * 48)
        expired = Session(uuid4(), uuid4(), datetime.now(UTC) - timedelta(seconds=10))
        with self.assertRaises(AuthenticationError):
            codec.decode(codec.encode(expired))
        valid = Session(uuid4(), uuid4(), datetime.now(UTC) + timedelta(minutes=5))
        with self.assertRaises(AuthenticationError):
            codec.decode(JwtTokenCodec("b" * 48).encode(valid))

    def test_password_spaces_preserved_and_role_rejected(self):
        password = "  a long password  "
        self.assertEqual(RegisterRequest(email="a@example.com", password=password).password, password)
        with self.assertRaises(ValidationError):
            RegisterRequest(email="a@example.com", password=password, role="ADMIN")


@unittest.skipUnless(os.getenv("RUN_DATABASE_TESTS") == "1", "Opt-in PostgreSQL integration test")
class AuthIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_account_isolation_logout_and_processing(self):
        import httpx
        from sqlalchemy import delete, update
        from email_assistant.basic.application.auth import AuthService
        from email_assistant.basic.application.services import ProcessEmailService, EmailHistoryService
        from email_assistant.basic.infrastructure.config import DatabaseSettings
        from email_assistant.basic.infrastructure.database import Database, SqlAlchemyEmailProcessingRepository
        from email_assistant.basic.infrastructure.database.auth_repository import SqlAlchemyAuthRepository
        from email_assistant.basic.infrastructure.database.models import UserRow, SessionRow, EmailProcessingRecordRow
        from email_assistant.basic.infrastructure.security import ArgonPasswordHasher
        from email_assistant.basic.interfaces.http.app import create_app
        from tests.basic.test_services import TrackingClassifier, RecordingResponder
        from email_assistant.basic.domain.models import TriageClassification

        db = Database(DatabaseSettings().database_url.get_secret_value())
        repo = SqlAlchemyEmailProcessingRepository(db.sessions)
        auth = AuthService(SqlAlchemyAuthRepository(db.sessions), ArgonPasswordHasher(), JwtTokenCodec("t" * 48))
        classifier = TrackingClassifier(TriageClassification.RESPOND)
        app = create_app(ProcessEmailService(classifier, RecordingResponder(), repo), EmailHistoryService(repo), auth)
        ids = []
        payload = {"author": "sender@example.com", "to": "recipient@example.com",
                   "subject": "Auth test", "email_thread": "Please reply"}
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                for endpoint, body in [("/emails/process", payload), ("/emails/process/batch", {"emails": [payload]}), ("/emails/process/stream", payload)]:
                    self.assertEqual((await client.post(endpoint, json=body)).status_code, 401)
                headers = []
                for _ in range(3):
                    credentials = {"email": f"auth-test-{uuid4()}@example.com", "password": " a password with spaces "}
                    registered = await client.post("/auth/register", json=credentials)
                    self.assertEqual(registered.status_code, 201, registered.text)
                    from uuid import UUID
                    ids.append(UUID(registered.json()["id"]))
                    self.assertNotIn("password_hash", registered.text)
                    self.assertEqual(registered.json()["role"], "USER")
                    self.assertEqual((await client.post("/auth/login", json={**credentials, "password": "wrong"})).status_code, 401)
                    token = (await client.post("/auth/login", json=credentials)).json()["access_token"]
                    headers.append({"Authorization": f"Bearer {token}"})
                async with db.sessions.begin() as session:
                    await session.execute(update(UserRow).where(UserRow.id == ids[2]).values(role="ADMIN"))
                response = await client.post("/emails/process", json=payload, headers=headers[0])
                self.assertEqual(response.status_code, 200, response.text)
                record_id = response.json()["record_id"]
                path = f"/emails/history/{record_id}"
                self.assertEqual((await client.get(path, headers=headers[1])).status_code, 404)
                self.assertEqual((await client.delete(path, headers=headers[1])).status_code, 404)
                self.assertEqual((await client.get("/emails/history", headers=headers[1])).json()["items"], [])
                self.assertEqual((await client.get(path, headers=headers[2])).status_code, 200)
                batch = await client.post("/emails/process/batch", json={"emails": [payload, payload]}, headers=headers[0])
                self.assertEqual(batch.status_code, 200, batch.text)
                stream = await client.post("/emails/process/stream", json=payload, headers=headers[0])
                self.assertIn("event: completed", stream.text)
                self.assertEqual((await client.delete(path, headers=headers[0])).status_code, 204)
                self.assertEqual((await client.post("/auth/logout", headers=headers[0])).status_code, 204)
                self.assertEqual((await client.get("/users/me", headers=headers[0])).status_code, 401)
                async with db.sessions.begin() as session:
                    await session.execute(update(UserRow).where(UserRow.id == ids[1]).values(is_active=False))
                self.assertEqual((await client.get("/users/me", headers=headers[1])).status_code, 401)
        finally:
            async with db.sessions.begin() as session:
                await session.execute(delete(EmailProcessingRecordRow).where(EmailProcessingRecordRow.owner_id.in_(ids)))
                await session.execute(delete(SessionRow).where(SessionRow.user_id.in_(ids)))
                await session.execute(delete(UserRow).where(UserRow.id.in_(ids)))
            await db.dispose()
