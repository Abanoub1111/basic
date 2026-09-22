"""Small live-model evaluation set, not exhaustive proof of model quality."""
import asyncio
import os
from dataclasses import replace

import pytest

from email_assistant.basic.infrastructure.groq_classifier import GroqEmailClassifier

pytestmark = pytest.mark.ai


@pytest.fixture
def live_classifier():
    key = os.getenv('GROQ_API_KEY')
    if not key:
        pytest.fail('Set GROQ_API_KEY before opting into live AI tests')
    return GroqEmailClassifier(api_key=key)


async def classify(model, email):
    # Bound network time; do not retry away a bad evaluation result.
    return await asyncio.wait_for(model.classify(email), timeout=60)


@pytest.mark.parametrize('subject,thread,expected', [
    ('Sale', 'Marketing newsletter: buy our discounted shoes today! Unsubscribe here.', 'ignore'),
    ('Deployment update', 'The build deployed successfully. Status update only; no action needed.', 'notify'),
    ('API question', 'Can you explain how authentication works in our API? Please reply.', 'respond'),
])
async def test_minimum_functionality(live_classifier, email, subject, thread, expected):
    result = await classify(live_classifier, replace(email, subject=subject, thread=thread))
    assert result.classification.value == expected
    assert result.reasoning.strip()


@pytest.mark.parametrize('change', ['uppercase', 'whitespace'])
async def test_invariance_to_harmless_changes(live_classifier, email, change):
    original = await classify(live_classifier, email)
    modified = replace(email, thread=email.thread.upper() if change == 'uppercase' else f'  {email.thread}  ')
    result = await classify(live_classifier, modified)
    assert original.classification.value == 'respond'
    assert result.classification == original.classification


async def test_direction_changes_when_a_reply_is_requested(live_classifier, email):
    update = replace(email, subject='Project update',
                     thread='The project deployment is complete. Status update only; no action needed.')
    request = replace(update, thread='The project deployment is complete. Can you review it and reply with approval?')
    before = await classify(live_classifier, update)
    after = await classify(live_classifier, request)
    assert before.classification.value == 'notify'
    assert after.classification.value == 'respond'
