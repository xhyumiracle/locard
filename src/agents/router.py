"""
Router Agent - Routes user input to appropriate workflow.

The Router Agent analyzes user input and decides whether to:
- Route to trace workflow (blockchain forensics tasks)
- Route to fallback workflow (general tool usage)
- Route to chat (simple conversation)
"""

from typing import Literal
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage

import config


class RouterOutput(TypedDict):
    route: Literal["trace", "fallback", "chat"]
    why: str


ROUTER_SYSTEM_PROMPT = """You are the Router Agent. Your sole responsibility is to route the user input to one of three options: `trace`, `fallback`, or `chat`.

Rules (in priority order):
1) If the user input is about blockchain analysis, such as tracing, forensics, cross-chain linkage, transaction attribution, fund flow provenance, or contains txhash/address/chain/bridge-like indicators, choose `trace`.
2) If the input requires external information or tool usage but is not clearly a blockchain tracing task, choose `fallback`.
3) Otherwise, choose `chat`.

Indicators that suggest `trace`:
- Transaction hashes (long hex strings like 0x... or alphanumeric strings for BTC/DOGE)
- Blockchain addresses (BTC: 1/3/bc1 prefix, DOGE: D prefix, ETH: 0x prefix)
- Keywords: trace, track, follow, source, origin, fund flow, cross-chain, bridge, swap, exchange
- Chain names: BTC, Bitcoin, ETH, Ethereum, DOGE, Dogecoin, etc.
- Questions about where funds came from or went to

Do not call any tools. Do not answer the user question. Do not modify any state.
Just analyze the input and return your routing decision."""


class RouterAgent:
    """Router Agent that decides which workflow to use."""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=config.LLM_MODEL,
            temperature=0,
            max_tokens=100
        ).with_structured_output(RouterOutput)

    def route(self, user_input: str) -> RouterOutput:
        """
        Analyze user input and return routing decision.

        Args:
            user_input: The user's message

        Returns:
            RouterOutput with route and explanation
        """
        messages = [
            SystemMessage(content=ROUTER_SYSTEM_PROMPT),
            {"role": "user", "content": user_input}
        ]

        result = self.llm.invoke(messages)
        return result


def create_router_node(state):
    """
    LangGraph node function for the Router Agent.

    Args:
        state: Current GraphState

    Returns:
        State update with routing decision
    """
    router = RouterAgent()

    # Get the latest user message
    messages = state.get("messages", [])
    if not messages:
        return {"current_subgraph": "chat"}

    last_message = messages[-1]
    user_input = last_message.content if hasattr(last_message, "content") else str(last_message)

    result = router.route(user_input)

    return {"current_subgraph": result["route"]}
