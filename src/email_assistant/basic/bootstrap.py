from dotenv import load_dotenv

from email_assistant.basic.application.services import ProcessEmailService
from email_assistant.basic.infrastructure.config import AppSettings
from email_assistant.basic.infrastructure.groq_classifier import (
    GroqEmailClassifier,
)
from email_assistant.basic.infrastructure.langgraph_response_agent import (
    LangGraphEmailResponder,
)
from email_assistant.tools import get_tools


def build_process_email_service(
    settings: AppSettings | None = None,
) -> ProcessEmailService:
    """Build the email-processing service with real dependencies."""

    if settings is None:
        load_dotenv()
        settings = AppSettings()

    groq_api_key = settings.groq_api_key.get_secret_value()

    classifier = GroqEmailClassifier(api_key=groq_api_key)
    responder = LangGraphEmailResponder(
        api_key=groq_api_key,
        tools=get_tools(),
    )

    return ProcessEmailService(
        classifier=classifier,
        responder=responder,
    )
