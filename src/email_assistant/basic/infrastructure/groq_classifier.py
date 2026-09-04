from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

from email_assistant.basic.application.ports import EmailClassifier
from email_assistant.basic.domain.models import (
    Email,
    TriageClassification,
    TriageResult,
)
from email_assistant.prompts import (
    default_background,
    default_triage_instructions,
    triage_system_prompt,
    triage_user_prompt,
)


class RouterOutput(BaseModel):
    """Structured output expected from the classifier model."""

    reasoning: str = Field(
        description="Reasoning behind the classification."
    )
    classification: TriageClassification = Field(
        description="Whether to respond, notify, or ignore."
    )


class GroqEmailClassifier(EmailClassifier):
    """Classify emails using a Groq-hosted language model."""

    def __init__(
        self,
        model_name: str = "openai/gpt-oss-20b",
        temperature: float = 0.0,
    ) -> None:
        model = init_chat_model(
            model_name,
            model_provider="groq",
            temperature=temperature,
        )

        self._router = model.with_structured_output(RouterOutput)

    def classify(self, email: Email) -> TriageResult:
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

        output = self._router.invoke(
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

        return TriageResult(
            classification=output.classification,
            reasoning=output.reasoning,
        )