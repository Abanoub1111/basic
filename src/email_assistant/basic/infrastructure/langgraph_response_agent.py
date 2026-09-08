from collections.abc import Sequence
from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, ConfigDict, Field

from email_assistant.basic.application.ports import EmailResponder
from email_assistant.basic.domain.models import Email, EmailReply
from email_assistant.basic.infrastructure.email_formatter import (
    format_email_markdown,
)
from email_assistant.basic.infrastructure.prompts import (
    agent_system_prompt,
    default_background,
    default_cal_preferences,
    default_response_preferences,
)
from email_assistant.tools.default.prompt_templates import AGENT_TOOLS_PROMPT


class WriteEmailToolCall(BaseModel):
    """Validated arguments captured from the write_email tool call."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    to: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    content: str = Field(min_length=1)

    def to_domain(self) -> EmailReply:
        """Convert provider-facing tool arguments into a domain reply."""

        return EmailReply(
            recipient=self.to,
            subject=self.subject,
            content=self.content,
        )


class LangGraphEmailResponder(EmailResponder):
    """Respond to emails using a LangGraph tool-calling workflow."""

    def __init__(
        self,
        api_key: str,
        tools: Sequence[BaseTool],
        model_name: str = "openai/gpt-oss-20b",
        temperature: float = 0.0,
        max_iterations: int = 10,
    ) -> None:
        self._tools = list(tools)
        self._max_iterations = max_iterations

        model = init_chat_model(
            model_name,
            model_provider="groq",
            temperature=temperature,
            api_key=api_key,
        )

        self._model_with_tools = model.bind_tools(
            self._tools,
            tool_choice="any",
        )

        self._system_message = SystemMessage(
            content=agent_system_prompt.format(
                tools_prompt=AGENT_TOOLS_PROMPT,
                background=default_background,
                response_preferences=default_response_preferences,
                cal_preferences=default_cal_preferences,
            )
        )

        graph_builder = StateGraph(MessagesState)
        graph_builder.add_node("agent", self._call_model)
        graph_builder.add_node("tools", ToolNode(self._tools))
        graph_builder.add_edge(START, "agent")
        graph_builder.add_conditional_edges(
            "agent",
            self._route_after_model,
            {
                "tools": "tools",
                END: END,
            },
        )
        graph_builder.add_conditional_edges(
            "tools",
            self._route_after_tools,
            {
                "agent": "agent",
                END: END,
            },
        )

        self._graph = graph_builder.compile()

    async def _call_model(
        self,
        state: MessagesState,
    ) -> dict[str, list[BaseMessage]]:
        """Ask the model for the next action in the graph."""

        response = await self._model_with_tools.ainvoke(
            [self._system_message, *state["messages"]]
        )

        return {"messages": [response]}

    @staticmethod
    def _route_after_model(
        state: MessagesState,
    ) -> Literal["tools", "__end__"]:
        """Route tool calls to execution or finish on the Done tool."""

        last_message = state["messages"][-1]

        if not isinstance(last_message, AIMessage):
            return END

        if any(
            tool_call["name"] == "Done"
            for tool_call in last_message.tool_calls
        ):
            return END

        if last_message.tool_calls:
            return "tools"

        return END

    @staticmethod
    def _route_after_tools(
        state: MessagesState,
    ) -> Literal["agent", "__end__"]:
        """Finish after drafting a reply; continue after support tools."""

        for message in reversed(state["messages"]):
            if isinstance(message, AIMessage):
                break

            if (
                isinstance(message, ToolMessage)
                and message.name == "write_email"
            ):
                return END

        return "agent"

    async def respond(self, email: Email) -> EmailReply:
        """Use the model and available tools to respond to an email."""

        email_markdown = format_email_markdown(
            email.subject,
            email.author,
            email.recipient,
            email.thread,
        )

        try:
            graph_result = await self._graph.ainvoke(
                {
                    "messages": [
                        HumanMessage(
                            content=(
                                f"Respond to the email: {email_markdown}"
                            )
                        )
                    ]
                },
                config={
                    "recursion_limit": self._max_iterations * 2 + 1,
                },
            )
        except GraphRecursionError as error:
            raise RuntimeError(
                "The response agent exceeded its maximum number of iterations."
            ) from error

        return self._extract_reply(graph_result["messages"])

    @staticmethod
    def _extract_reply(messages: Sequence[BaseMessage]) -> EmailReply:
        """Extract the latest validated write_email call from graph state."""

        for message in reversed(messages):
            if not isinstance(message, AIMessage):
                continue

            for tool_call in reversed(message.tool_calls):
                if tool_call["name"] == "write_email":
                    return WriteEmailToolCall.model_validate(
                        tool_call["args"]
                    ).to_domain()

        raise RuntimeError(
            "The response workflow completed without drafting an email."
        )
