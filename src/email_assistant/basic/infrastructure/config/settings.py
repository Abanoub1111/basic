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
    jwt_secret: SecretStr = Field(min_length=32)
    access_token_minutes: int = Field(default=30, ge=1, le=60)
    langsmith_api_key: SecretStr | None = None
    groq_max_concurrency: int = Field(default=3, ge=1, le=20)
    emails_per_minute: int = Field(default=20, ge=1)
    login_ip_per_minute: int = Field(default=10, ge=1)
    login_email_per_minute: int = Field(default=5, ge=1)
    classification_cache_enabled: bool = True
    classification_cache_ttl_seconds: int = Field(default=300, ge=1)
    classification_cache_max_entries: int = Field(default=1000, ge=1)

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
