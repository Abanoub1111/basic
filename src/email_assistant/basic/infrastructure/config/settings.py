from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Validated settings loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    groq_api_key: SecretStr
    langsmith_api_key: SecretStr | None = None

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
