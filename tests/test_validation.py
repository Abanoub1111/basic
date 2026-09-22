"""Parameterized valid, invalid, and boundary inputs."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from email_assistant.basic.application.auth import AuthenticationError, Session
from email_assistant.basic.infrastructure.security import JwtTokenCodec
from email_assistant.basic.interfaces.http.auth import RegisterRequest
from email_assistant.basic.interfaces.http.schemas import ProcessEmailRequest
from email_assistant.tools.default.calendar_tools import schedule_meeting


@pytest.mark.parametrize('subject,valid', [('Hello', True), ('  Hello  ', True),
                                        ('', False), ('   ', False),
                                        ('x' * 500, True), ('x' * 501, False)])
def test_subject_validation(payload, subject, valid):
    payload['subject'] = subject
    if valid:
        assert ProcessEmailRequest(**payload).subject == subject.strip()
    else:
        with pytest.raises(ValidationError):
            ProcessEmailRequest(**payload)


@pytest.mark.parametrize('extra', [{'unexpected': True}, {'email_thread': 'x' * 10001}])
def test_rejects_extra_fields_and_oversized_thread(payload, extra):
    with pytest.raises(ValidationError):
        ProcessEmailRequest(**(payload | extra))


def test_password_preserved_and_role_cannot_be_chosen():
    credentials = dict(email='a@example.com', password='  a long password  ')
    assert RegisterRequest(**credentials).password == credentials['password']
    with pytest.raises(ValidationError):
        RegisterRequest(**credentials, role='ADMIN')


@pytest.mark.parametrize('expired,wrong_key', [(False, False), (True, False), (False, True)])
def test_token_validation(expired, wrong_key):
    codec = JwtTokenCodec('a' * 48)
    session = Session(uuid4(), uuid4(), datetime.now(timezone.utc) +
                      timedelta(minutes=-5 if expired else 5))
    token = JwtTokenCodec(('b' if wrong_key else 'a') * 48).encode(session)
    if expired or wrong_key:
        with pytest.raises(AuthenticationError):
            codec.decode(token)
    else:
        assert codec.decode(token).user_id == session.user_id


def test_calendar_accepts_iso_date():
    result = schedule_meeting.invoke(dict(attendees=['manager@example.com'], subject='Project',
                                          duration_minutes=30, preferred_day='2026-09-06', start_time=14))
    assert 'September 06, 2026' in result
