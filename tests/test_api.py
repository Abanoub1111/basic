"""API workflows: real HTTP routes/services, in-memory storage, stubbed AI/auth."""
import json
from dataclasses import replace
from uuid import uuid4

import pytest


def test_process_read_and_delete_history(client, payload, headers):
    response = client.post('/emails/process', json=payload, headers=headers)
    assert response.status_code == 200
    result = response.json()
    assert result['action'] == 'responded'
    path = f"/emails/history/{result['record_id']}"
    stored = client.get(path, headers=headers)
    assert stored.status_code == 200
    assert stored.json()['result'] == result
    assert len(client.get('/emails/history', headers=headers).json()['items']) == 1
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get(path, headers=headers).status_code == 404


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
