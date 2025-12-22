"""
Chat Agent - Handles simple conversational queries.

For queries that don't require tools or blockchain analysis.
"""

from typing import List

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, BaseMessage, AIMessage

import config
from src.state.graph_state import GraphState


CHAT_SYSTEM_PROMPT = """You are a helpful assistant specializing in blockchain analysis and forensics. You're part of the BlockchainMAS (Multi-Agent System) that can trace transactions across different blockchains.

When users have simple questions or greetings, respond naturally. If they ask about blockchain-specific analysis tasks (like tracing transactions, finding fund sources, cross-chain analysis), let them know you can help with that and they can provide transaction details.

You can help with:
- Explaining blockchain concepts (UTXO, account model, cross-chain bridges)
- General questions about Bitcoin, Dogecoin, Ethereum
- Guidance on how to use this system for tracing

Keep responses concise and helpful."""


class ChatAgent:
    """Simple chat agent for non-tool conversations."""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=config.LLM_MODEL,
            temperature=0.7,  # Slightly creative for chat
            max_tokens=config.LLM_MAX_TOKENS
        )

    def respond(self, state: GraphState) -> str:
        """
        Generate a response to the conversation.

        Args:
            state: Current graph state with messages

        Returns:
            Response text
        """
        messages = self._build_messages(state)
        response = self.llm.invoke(messages)
        return response.content

    def _build_messages(self, state: GraphState) -> List[BaseMessage]:
        """Build messages for LLM."""
        messages = [SystemMessage(content=CHAT_SYSTEM_PROMPT)]

        conv_messages = state.get("messages", [])
        for msg in conv_messages:
            messages.append(msg)

        return messages


def create_chat_response(state: GraphState) -> dict:
    """
    Create chat response and return state update.

    Args:
        state: Current graph state

    Returns:
        State update with AI response message
    """
    agent = ChatAgent()
    response = agent.respond(state)

    return {
        "messages": [AIMessage(content=response)]
    }
