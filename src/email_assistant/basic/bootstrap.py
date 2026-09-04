from dotenv import load_dotenv

from email_assistant.basic.application.services import ProcessEmailService
from email_assistant.basic.infrastructure.groq_classifier import (
    GroqEmailClassifier,
)
from email_assistant.basic.infrastructure.langchain_response_agent import (
    LangChainEmailResponder,
)


def build_process_email_service() -> ProcessEmailService:
    """Build the email-processing service with real dependencies."""

    load_dotenv()

    classifier = GroqEmailClassifier()
    responder = LangChainEmailResponder()

    return ProcessEmailService(
        classifier=classifier,
        responder=responder,
    )