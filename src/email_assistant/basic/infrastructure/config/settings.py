from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database settings usable independently by Alembic."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: SecretStr = SecretStr(
        "postgresql+asyncpg://email_assistant:email_assistant@localhost:5433/"
        "email_assistant"
    )
    database_echo: bool = False


class AppSettings(DatabaseSettings):
    """Validated settings loaded from environment variables or a .env file."""

    groq_api_key: SecretStr
    langsmith_api_key: SecretStr | None = None
    groq_max_concurrency: int = Field(default=3, ge=1, le=20)

    @field_validator("groq_api_key", "langsmith_api_key")
    @classmethod
    def reject_blank_secrets(
        cls,
        value: SecretStr | None,
    ) -> SecretStr | None:
        """Reject configured secrets that contain only whitespace."""

        if value is not None and not value.get_secret_value().strip():
            raise ValueError("API keys cannot be blank")

        return value
