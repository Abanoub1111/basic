"""Fresh fixtures keep tests independent; external services are opt-in."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from email_assistant.basic.application.auth import AuthenticationError
from email_assistant.basic.application.services import EmailHistoryService, ProcessEmailService
from email_assistant.basic.application.usage import UsageLimits
from email_assistant.basic.domain.models import Email, EmailReply, TriageClassification, TriageResult
from email_assistant.basic.domain.users import User, UserRole
from email_assistant.basic.infrastructure.classification_cache import InMemoryClassificationCache
from email_assistant.basic.infrastructure.usage_counter import InMemoryUsageCounter
from email_assistant.basic.interfaces.http.app import create_app
from tests.fakes import MemoryRepository


def pytest_addoption(parser):
    parser.addoption('--run-database', action='store_true', help='Run PostgreSQL tests')
    parser.addoption('--run-ai', action='store_true', help='Run live Groq evaluations')


def pytest_collection_modifyitems(config, items):
    for item in items:
        for marker, flag in [('database', '--run-database'), ('ai', '--run-ai')]:
            if marker in item.keywords and not config.getoption(flag):
                item.add_marker(pytest.mark.skip(reason=f'Opt in with {flag}'))


@pytest.fixture
def user():
    return User(uuid4(), 'tester@example.com', UserRole.USER, True)


@pytest.fixture
def email():
    return Email('sender@example.com', 'assistant@example.com',
                 'Project question', 'Could you explain the project status?')


@pytest.fixture
def payload(email):
    return dict(author=email.author, to=email.recipient,
                subject=email.subject, email_thread=email.thread)


@pytest.fixture
def repository():
    return MemoryRepository()


@pytest.fixture
def classifier():
    classifier = AsyncMock()
    classifier.classify.return_value = TriageResult(TriageClassification.RESPOND, 'Reply requested')
    return classifier


@pytest.fixture
def responder(email):
    responder = AsyncMock()
    responder.respond.return_value = EmailReply(email.author, 'Re: Project question', 'I will check.')
    return responder


@pytest.fixture
def now():
    # Tests advance this clock instantly instead of sleeping.
    return [0.0]


@pytest.fixture
def service(classifier, responder, repository, now):
    return ProcessEmailService(classifier, responder, repository, max_concurrency=2,
                               classification_cache=InMemoryClassificationCache(clock=lambda: now[0]))


@pytest.fixture
def auth(user):
    auth = AsyncMock()

    async def current_user(token):
        if token != 'test':
            raise AuthenticationError()
        return user

    auth.current_user.side_effect = current_user
    auth.login.side_effect = AuthenticationError()
    return auth


@pytest.fixture
def client(service, repository, auth, now):
    usage = UsageLimits(InMemoryUsageCounter(lambda: now[0]), emails_per_minute=4,
                        login_ip_per_minute=2, login_email_per_minute=1)
    app = create_app(service, EmailHistoryService(repository), auth, usage)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def headers():
    return {'Authorization': 'Bearer test'}
