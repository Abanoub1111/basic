from langchain.chat_models import init_chat_model
from pydantic import BaseModel, ConfigDict, Field

from email_assistant.basic.application.ports import EmailClassifier
from email_assistant.basic.domain.models import (
    Email,
    TriageClassification,
    TriageResult,
)
from email_assistant.basic.infrastructure.prompts import (
    default_background,
    default_triage_instructions,
    triage_system_prompt,
    triage_user_prompt,
)


class RouterOutput(BaseModel):
    """Validated structured output used only by the Groq classifier."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    reasoning: str = Field(
        min_length=1,
        max_length=2_000,
        description="Reasoning behind the classification.",
    )
    classification: TriageClassification = Field(
        description="Whether to respond, notify, or ignore."
    )


class GroqEmailClassifier(EmailClassifier):
    """Classify emails using a Groq-hosted language model."""

    def __init__(
        self,
        api_key: str,
        model_name: str = "openai/gpt-oss-20b",
        temperature: float = 0.0,
    ) -> None:
        model = init_chat_model(
            model_name,
            model_provider="groq",
            temperature=temperature,
            api_key=api_key,
        )

        self._router = model.with_structured_output(RouterOutput)

    async def classify(self, email: Email) -> TriageResult:
        """Classify an email using the language model."""

        system_prompt = triage_system_prompt.format(
            background=default_background,
            triage_instructions=default_triage_instructions,
        )

        user_prompt = triage_user_prompt.format(
            author=email.author,
            to=email.recipient,
            subject=email.subject,
            email_thread=email.thread,
        )

        output = RouterOutput.model_validate(
            await self._router.ainvoke(
                [
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_prompt,
                    },
                ]
            )
        )

        return TriageResult(
            classification=output.classification,
            reasoning=output.reasoning,
        )
