from dataclasses import dataclass

from dotenv import load_dotenv
from email_assistant.basic.application.auth import AuthService
from email_assistant.basic.infrastructure.database.auth_repository import SqlAlchemyAuthRepository
from email_assistant.basic.infrastructure.security import ArgonPasswordHasher, JwtTokenCodec

from email_assistant.basic.application.services import (
    EmailHistoryService,
    ProcessEmailService,
)
from email_assistant.basic.infrastructure.config import AppSettings
from email_assistant.basic.infrastructure.database import (
    Database,
    SqlAlchemyEmailProcessingRepository,
)
from email_assistant.basic.infrastructure.groq_classifier import (
    GroqEmailClassifier,
)
from email_assistant.basic.infrastructure.langgraph_response_agent import (
    LangGraphEmailResponder,
)
from email_assistant.tools import get_tools


@dataclass(frozen=True)
class ApplicationContainer:
    """Objects shared for the lifetime of the running application."""

    process_email_service: ProcessEmailService
    email_history_service: EmailHistoryService
    database: Database
    auth_service: AuthService


def build_application(
    settings: AppSettings | None = None,
) -> ApplicationContainer:
    """Build application services and their real dependencies."""

    if settings is None:
        load_dotenv()
        settings = AppSettings()

    groq_api_key = settings.groq_api_key.get_secret_value()

    classifier = GroqEmailClassifier(api_key=groq_api_key)
    responder = LangGraphEmailResponder(
        api_key=groq_api_key,
        tools=get_tools(),
    )
    database = Database(
        settings.database_url.get_secret_value(),
        echo=settings.database_echo,
    )
    repository = SqlAlchemyEmailProcessingRepository(database.sessions)

    return ApplicationContainer(
        process_email_service=ProcessEmailService(
            classifier=classifier,
            responder=responder,
            repository=repository,
            max_concurrency=settings.groq_max_concurrency,
        ),
        email_history_service=EmailHistoryService(repository),
        database=database,
        auth_service=AuthService(SqlAlchemyAuthRepository(database.sessions),
                                 ArgonPasswordHasher(), JwtTokenCodec(settings.jwt_secret.get_secret_value()),
                                 settings.access_token_minutes),
    )
