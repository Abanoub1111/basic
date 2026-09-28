"""Optional PostgreSQL integration and user workflow tests. AI stays stubbed."""
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select

from email_assistant.basic.application.auth import AuthService
from email_assistant.basic.application.services import EmailHistoryService, ProcessEmailService
from email_assistant.basic.application.usage import UsageLimits
from email_assistant.basic.infrastructure.database import Database, SqlAlchemyEmailProcessingRepository
from email_assistant.basic.infrastructure.database.auth_repository import SqlAlchemyAuthRepository
from email_assistant.basic.infrastructure.database.models import UserRow, SessionRow, EmailProcessingRecordRow
from email_assistant.basic.infrastructure.security import ArgonPasswordHasher, JwtTokenCodec
from email_assistant.basic.infrastructure.usage_counter import InMemoryUsageCounter
from email_assistant.basic.interfaces.http.app import create_app

pytestmark = pytest.mark.database


@pytest.fixture
async def database():
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.fail('Set TEST_DATABASE_URL to a migrated, disposable PostgreSQL database')
    db = Database(url)
    # Exact unique addresses limit cleanup to accounts created by this fixture.
    addresses = [f'ch11-{uuid4()}@example.com' for _ in range(2)]
    try:
        yield db, addresses
    finally:
        try:
            async with db.sessions.begin() as session:
                ids = select(UserRow.id).where(UserRow.email.in_(addresses))
                await session.execute(delete(EmailProcessingRecordRow).where(EmailProcessingRecordRow.owner_id.in_(ids)))
                await session.execute(delete(SessionRow).where(SessionRow.user_id.in_(ids)))
                await session.execute(delete(UserRow).where(UserRow.email.in_(addresses)))
        finally:
            await db.dispose()


@pytest.fixture
def real_auth(database):
    db, _ = database
    return AuthService(SqlAlchemyAuthRepository(db.sessions), ArgonPasswordHasher(), JwtTokenCodec('t' * 48))


async def test_repository_round_trip(database, real_auth, email):
    db, addresses = database
    user = await real_auth.register(addresses[0], 'a long test password')
    repo = SqlAlchemyEmailProcessingRepository(db.sessions)
    record = await repo.create(email, user.id)
    assert (await repo.get(record.id, owner_id=user.id)).email == email
    assert await repo.get(record.id, owner_id=uuid4()) is None
    await repo.fail(record.id, 'Test failure')
    assert (await repo.get(record.id, owner_id=user.id)).failure_message == 'Test failure'
    assert await repo.delete(record.id, owner_id=user.id)
    assert await repo.get(record.id) is None


async def test_register_login_process_history_logout(database, real_auth, classifier, responder, payload):
    db, addresses = database
    repo = SqlAlchemyEmailProcessingRepository(db.sessions)
    app = create_app(ProcessEmailService(classifier, responder, repo), EmailHistoryService(repo),
                     real_auth, UsageLimits(InMemoryUsageCounter()))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        tokens = []
        for address in addresses:
            credentials = dict(email=address, password='a long test password')
            registered = await client.post('/auth/register', json=credentials)
            assert registered.status_code == 201
            assert 'password_hash' not in registered.text
            login = await client.post('/auth/login', json=credentials)
            assert login.status_code == 200
            tokens.append({'Authorization': f"Bearer {login.json()['access_token']}"})
        response = await client.post('/emails/process', json=payload, headers=tokens[0])
        assert response.status_code == 200
        path = f"/emails/history/{response.json()['record_id']}"
        history = await client.get(path, headers=tokens[0])
        assert history.status_code == 200
        assert history.json()['result'] == response.json()
        assert (await client.get(path, headers=tokens[1])).status_code == 404
        assert (await client.delete(path, headers=tokens[1])).status_code == 404
        assert (await client.delete(path, headers=tokens[0])).status_code == 204
        assert (await client.post('/auth/logout', headers=tokens[0])).status_code == 204
        assert (await client.get('/users/me', headers=tokens[0])).status_code == 401
