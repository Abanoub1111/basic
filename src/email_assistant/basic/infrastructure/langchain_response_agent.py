from langchain.chat_models import init_chat_model
from langchain_core.messages import ToolMessage

from email_assistant.basic.application.ports import EmailResponder
from email_assistant.basic.domain.models import Email
from email_assistant.prompts import (
    agent_system_prompt,
    default_background,
    default_cal_preferences,
    default_response_preferences,
)
from email_assistant.tools import get_tools, get_tools_by_name
from email_assistant.tools.default.prompt_templates import AGENT_TOOLS_PROMPT
from email_assistant.utils import format_email_markdown


class LangChainEmailResponder(EmailResponder):
    """Respond to emails using a LangChain tool-calling agent."""

    def __init__(
        self,
        model_name: str = "openai/gpt-oss-20b",
        temperature: float = 0.0,
        max_iterations: int = 10,
    ) -> None:
        self._tools = get_tools()
        self._tools_by_name = get_tools_by_name(self._tools)
        self._max_iterations = max_iterations

        model = init_chat_model(
            model_name,
            model_provider="groq",
            temperature=temperature,
        )

        self._model_with_tools = model.bind_tools(
            self._tools,
            tool_choice="any",
        )

    def respond(self, email: Email) -> None:
        """Use the model and available tools to respond to an email."""

        email_markdown = format_email_markdown(
            email.subject,
            email.author,
            email.recipient,
            email.thread,
        )

        system_message = {
            "role": "system",
            "content": agent_system_prompt.format(
                tools_prompt=AGENT_TOOLS_PROMPT,
                background=default_background,
                response_preferences=default_response_preferences,
                cal_preferences=default_cal_preferences,
            ),
        }

        messages = [
            {
                "role": "user",
                "content": f"Respond to the email: {email_markdown}",
            }
        ]

        for _ in range(self._max_iterations):
            assistant_message = self._model_with_tools.invoke(
                [system_message, *messages]
            )

            messages.append(assistant_message)

            tool_calls = assistant_message.tool_calls

            if not tool_calls:
                return

            if any(
                tool_call["name"] == "Done"
                for tool_call in tool_calls
            ):
                return

            for tool_call in tool_calls:
                tool = self._tools_by_name.get(tool_call["name"])

                if tool is None:
                    raise ValueError(
                        f"Unknown tool requested: {tool_call['name']}"
                    )

                observation = tool.invoke(tool_call["args"])

                messages.append(
                    ToolMessage(
                        content=str(observation),
                        tool_call_id=tool_call["id"],
                    )
                )

        raise RuntimeError(
            "The response agent exceeded its maximum number of iterations."
        )