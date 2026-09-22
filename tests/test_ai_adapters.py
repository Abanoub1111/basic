"""Offline adapter tests: patch the model boundary, run real conversion/graph code."""
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from email_assistant.basic.infrastructure import groq_classifier, langgraph_response_agent
from email_assistant.tools.default.email_tools import write_email


@pytest.mark.parametrize('output,valid', [
    ({'classification': 'respond', 'reasoning': 'Direct question'}, True),
    ({'classification': 'invalid', 'reasoning': 'Direct question'}, False),
    ({'classification': 'respond', 'reasoning': ' '}, False),
])
async def test_classifier_validates_provider_output(monkeypatch, email, output, valid):
    router = AsyncMock()
    router.ainvoke.return_value = output
    model = Mock()
    model.with_structured_output.return_value = router
    monkeypatch.setattr(groq_classifier, 'init_chat_model', Mock(return_value=model))
    classifier = groq_classifier.GroqEmailClassifier(api_key='test')
    if valid:
        result = await classifier.classify(email)
        assert result.classification.value == 'respond'
        assert result.reasoning == 'Direct question'
        messages = router.ainvoke.call_args.args[0]
        assert email.thread in messages[1]['content']
    else:
        with pytest.raises(ValidationError):
            await classifier.classify(email)


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
