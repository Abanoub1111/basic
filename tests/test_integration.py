"""Component interactions, plus opt-in PostgreSQL and live AI checks."""
from dataclasses import replace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
import asyncio
import json
import os

from langchain_core.messages import AIMessage
import pytest

from email_assistant.basic.infrastructure import langgraph_response_agent
from email_assistant.basic.infrastructure.database import SqlAlchemyEmailProcessingRepository
from email_assistant.basic.infrastructure.groq_classifier import GroqEmailClassifier
from email_assistant.tools.default.email_tools import write_email

# AI adapters and graph


async def test_response_graph_executes_tool_and_returns_reply(monkeypatch, email):
    bound_model = AsyncMock()
    bound_model.ainvoke.return_value = AIMessage(content='', tool_calls=[
        {'name': 'write_email', 'args': {'to': email.author, 'subject': 'Re: Project',
                                       'content': 'I will check the project status.'},
         'id': 'reply-1', 'type': 'tool_call'},
    ])
    model = Mock()
    model.bind_tools.return_value = bound_model
    monkeypatch.setattr(langgraph_response_agent, 'init_chat_model', Mock(return_value=model))
    responder = langgraph_response_agent.LangGraphEmailResponder(api_key='test', tools=[write_email])
    reply = await responder.respond(email)
    assert reply.recipient == email.author
    assert reply.content == 'I will check the project status.'
    assert bound_model.ainvoke.await_count == 1

# HTTP routes and workflows


def test_history_is_private(client, auth, user, payload, headers):
    result = client.post('/emails/process', json=payload, headers=headers).json()
    path = f"/emails/history/{result['record_id']}"
    auth.current_user.side_effect = None
    auth.current_user.return_value = replace(user, id=uuid4())
    assert client.get(path, headers=headers).status_code == 404
    assert client.delete(path, headers=headers).status_code == 404
    assert client.get('/emails/history', headers=headers).json()['items'] == []

def test_single_batch_stream_share_cache_and_quota(client, payload, headers, classifier, repository, now):
    assert client.post('/emails/process', json=payload, headers=headers).status_code == 200
    batch = client.post('/emails/process/batch', json={'emails': [payload, payload]}, headers=headers)
    assert batch.status_code == 200
    assert len(batch.json()['results']) == 2
    stream = client.post('/emails/process/stream', json=payload, headers=headers)
    assert stream.status_code == 200
    assert stream.headers['content-type'].startswith('text/event-stream')
    frames = stream.text.strip().split('\n\n')
    names = [frame.splitlines()[0] for frame in frames]
    assert names == ['event: started', 'event: classified', 'event: responding',
                     'event: reply_created', 'event: completed']
    for frame in frames:
        assert isinstance(json.loads(frame.splitlines()[1].removeprefix('data: ')), dict)
    assert classifier.classify.await_count == 1
    assert len(repository.records) == 4
    rejected = client.post('/emails/process/stream', json=payload, headers=headers)
    assert rejected.status_code == 429
    assert rejected.headers['Retry-After'] == '60'
    assert len(repository.records) == 4
    now[0] = 60
    assert client.post('/emails/process', json=payload, headers=headers).status_code == 200

@pytest.mark.parametrize('path', ['/emails/process', '/emails/process/batch', '/emails/process/stream'])
def test_processing_requires_authentication(client, payload, path):
    body = {'emails': [payload]} if path.endswith('/batch') else payload
    assert client.post(path, json=body).status_code == 401

def test_invalid_requests_do_not_spend_quota(client, payload, headers):
    assert client.post('/emails/process', json={}, headers=headers).status_code == 422
    assert client.post('/emails/process', json=payload).status_code == 401
    oversized = client.post('/emails/process/batch', json={'emails': [payload] * 5}, headers=headers)
    assert oversized.status_code == 422
    assert client.post('/emails/process/batch', json={'emails': [payload] * 4}, headers=headers).status_code == 200

def test_login_is_limited_before_password_check(client, auth):
    body = {'email': 'a@example.com', 'password': 'incorrect'}
    assert client.post('/auth/login', json=body).status_code == 401
    assert client.post('/auth/login', json=body).status_code == 429
    assert auth.login.await_count == 1
    assert client.post('/auth/login', json=body | {'email': 'b@example.com'}).status_code == 401
    assert client.post('/auth/login', json=body | {'email': 'c@example.com'}).status_code == 429
    assert auth.login.await_count == 2

def test_provider_failure_becomes_safe_stream_error(client, classifier, payload, headers):
    classifier.classify.side_effect = RuntimeError('Secret provider details')
    response = client.post('/emails/process/stream', json=payload, headers=headers)
    assert 'event: error' in response.text
    assert 'Email processing failed.' in response.text
    assert 'Secret provider details' not in response.text

# PostgreSQL (opt-in)


@pytest.mark.database
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

# Live AI behavior (opt-in)


@pytest.fixture
def live_classifier():
    key = os.getenv('GROQ_API_KEY')
    if not key:
        pytest.fail('Set GROQ_API_KEY before opting into live AI tests')
    return GroqEmailClassifier(api_key=key)

async def classify(model, email):
    # Bound network time; do not retry away a bad evaluation result.
    return await asyncio.wait_for(model.classify(email), timeout=60)

@pytest.mark.ai
@pytest.mark.parametrize('subject,thread,expected', [
    ('Sale', 'Marketing newsletter: buy our discounted shoes today! Unsubscribe here.', 'ignore'),
    ('Deployment update', 'The build deployed successfully. Status update only; no action needed.', 'notify'),
    ('API question', 'Can you explain how authentication works in our API? Please reply.', 'respond'),
])
async def test_minimum_functionality(live_classifier, email, subject, thread, expected):
    result = await classify(live_classifier, replace(email, subject=subject, thread=thread))
    assert result.classification.value == expected
    assert result.reasoning.strip()

@pytest.mark.ai
@pytest.mark.parametrize('change', ['uppercase', 'whitespace'])
async def test_invariance_to_harmless_changes(live_classifier, email, change):
    original = await classify(live_classifier, email)
    modified = replace(email, thread=email.thread.upper() if change == 'uppercase' else f'  {email.thread}  ')
    result = await classify(live_classifier, modified)
    assert original.classification.value == 'respond'
    assert result.classification == original.classification

@pytest.mark.ai
async def test_direction_changes_when_a_reply_is_requested(live_classifier, email):
    update = replace(email, subject='Project update',
                     thread='The project deployment is complete. Status update only; no action needed.')
    request = replace(update, thread='The project deployment is complete. Can you review it and reply with approval?')
    before = await classify(live_classifier, update)
    after = await classify(live_classifier, request)
    assert before.classification.value == 'notify'
    assert after.classification.value == 'respond'
