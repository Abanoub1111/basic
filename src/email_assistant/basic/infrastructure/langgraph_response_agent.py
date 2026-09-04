from collections.abc import Sequence
from typing import Literal

from langchain.chat_models import init_chat_model
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.tools import BaseTool
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from email_assistant.basic.application.ports import EmailResponder
from email_assistant.basic.domain.models import Email
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
        graph_builder.add_edge("tools", "agent")

        self._graph = graph_builder.compile()

    def _call_model(
        self,
        state: MessagesState,
    ) -> dict[str, list[BaseMessage]]:
        """Ask the model for the next action in the graph."""

        response = self._model_with_tools.invoke(
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

    def respond(self, email: Email) -> None:
        """Use the model and available tools to respond to an email."""

        email_markdown = format_email_markdown(
            email.subject,
            email.author,
            email.recipient,
            email.thread,
        )

        try:
            self._graph.invoke(
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
