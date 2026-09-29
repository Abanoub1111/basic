"""User workflows through HTTP. AI is mocked; PostgreSQL workflow is opt-in."""
import httpx
import pytest

from email_assistant.basic.application.services import ProcessEmailService, EmailHistoryService
from email_assistant.basic.application.usage import UsageLimits
from email_assistant.basic.infrastructure.database import SqlAlchemyEmailProcessingRepository
from email_assistant.basic.infrastructure.usage_counter import InMemoryUsageCounter
from email_assistant.basic.interfaces.http.app import create_app

# HTTP routes and workflows


@pytest.mark.database
async def test_process_read_and_delete_history(client, payload, headers):
    response = await client.post('/emails/process', json=payload, headers=headers)
    assert response.status_code == 200
    result = response.json()
    assert result['action'] == 'responded'
    path = f"/emails/history/{result['record_id']}"
    stored = await client.get(path, headers=headers)
    assert stored.status_code == 200
    assert stored.json()['result'] == result
    assert len((await client.get('/emails/history', headers=headers)).json()['items']) == 1
    assert (await client.delete(path, headers=headers)).status_code == 204
    assert (await client.get(path, headers=headers)).status_code == 404

# PostgreSQL (opt-in)


@pytest.mark.database
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
