"""
Router Agent - Routes user input to appropriate workflow.

The Router Agent analyzes user input and decides whether to:
- Route to trace workflow (blockchain forensics tasks)
- Route to fallback workflow (general tool usage)
- Route to chat (simple conversation)
"""

from typing import Literal
from typing_extensions import TypedDict

from langchain_core.messages import SystemMessage

import config
from src.prompts import load_prompt
from src.state.graph_state import Subgraph
from src.utils.debug import print_messages
from src.llm import create_chat_model

class RouterOutput(TypedDict):
    route: Subgraph

class RouterAgent:
    """Router Agent that decides which workflow to use."""

    def __init__(self):
        llm = create_chat_model(
            model=config.get_agent_model("router"),
            temperature=0,
            max_tokens=100
        )
        self.llm = llm.with_structured_output(RouterOutput)

    def route(self, user_input: str) -> RouterOutput:
        """
        Analyze user input and return routing decision.

        Args:
            user_input: The user's message

        Returns:
            RouterOutput with route and explanation
        """
        messages = [
            SystemMessage(content=load_prompt("router")),
            {"role": "user", "content": user_input}
        ]

        # Store for debugging
        self._last_messages = messages

        print_messages("router", "Input", messages)
        result = self.llm.invoke(messages)
        print_messages("router", "Output", result)
        return result