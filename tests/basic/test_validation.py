import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END

from email_assistant.basic.infrastructure.config import AppSettings
from email_assistant.basic.infrastructure.groq_classifier import RouterOutput
from email_assistant.basic.infrastructure.langgraph_response_agent import (
    LangGraphEmailResponder,
)
from email_assistant.basic.interfaces.http.schemas import (
    HealthResponse,
    ProcessEmailRequest,
)


class HttpSchemaTests(unittest.TestCase):
    def test_request_strips_whitespace(self) -> None:
        request = ProcessEmailRequest(
            author="  sender@example.com  ",
            to="recipient@example.com",
            subject="  Hello  ",
            email_thread="Message",
        )

        self.assertEqual(request.author, "sender@example.com")
        self.assertEqual(request.subject, "Hello")

    def test_request_rejects_blank_and_extra_fields(self) -> None:
        with self.assertRaises(ValidationError):
            ProcessEmailRequest(
                author="   ",
                to="recipient@example.com",
                subject="Hello",
                email_thread="Message",
                unexpected=True,
            )

    def test_health_status_is_fixed(self) -> None:
        with self.assertRaises(ValidationError):
            HealthResponse(status="unhealthy")


class LlmSchemaTests(unittest.TestCase):
    def test_router_output_rejects_invalid_model_data(self) -> None:
        with self.assertRaises(ValidationError):
            RouterOutput.model_validate(
                {
                    "classification": "respond",
                    "reasoning": "   ",
                    "unexpected": True,
                }
            )


class LangGraphRoutingTests(unittest.TestCase):
    def test_done_tool_ends_the_graph(self) -> None:
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "Done",
                    "args": {"done": True},
                    "id": "done-1",
                    "type": "tool_call",
                }
            ],
        )

        route = LangGraphEmailResponder._route_after_model(
            {"messages": [message]}
        )

        self.assertEqual(route, END)

    def test_regular_tool_call_routes_to_tools(self) -> None:
        message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "write_email",
                    "args": {
                        "to": "recipient@example.com",
                        "subject": "Hello",
                        "content": "Message",
                    },
                    "id": "tool-1",
                    "type": "tool_call",
                }
            ],
        )

        route = LangGraphEmailResponder._route_after_model(
            {"messages": [message]}
        )

        self.assertEqual(route, "tools")

    def test_non_ai_message_ends_the_graph(self) -> None:
        route = LangGraphEmailResponder._route_after_model(
            {"messages": [HumanMessage(content="Hello")]}
        )

        self.assertEqual(route, END)


class SettingsTests(unittest.TestCase):
    def test_settings_require_a_nonblank_groq_key(self) -> None:
        clean_environment = {
            key: value
            for key, value in os.environ.items()
            if key not in {"GROQ_API_KEY", "LANGSMITH_API_KEY"}
        }

        with patch.dict(os.environ, clean_environment, clear=True):
            with self.assertRaises(ValidationError):
                AppSettings(
                    _env_file=None,
                    groq_api_key="   ",
                )


if __name__ == "__main__":
    unittest.main()
