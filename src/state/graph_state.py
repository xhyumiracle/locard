"""
GraphState schema for BlockchainMAS LangGraph workflow.
"""

from typing import List, Literal, Optional, Annotated
from typing_extensions import TypedDict
import operator
import uuid

from langchain_core.messages import BaseMessage, HumanMessage

# Define Subgraph type here to avoid circular import with registry.py
Subgraph = Literal["tracetx"]  # will add more routes in the future

class GraphState(TypedDict, total=False):
    # identity / session
    thread_id: str

    # conversation (shared thread) - using Annotated for automatic merging
    messages: Annotated[List[BaseMessage], operator.add]

    # routing decision
    route: Optional[Subgraph]

    # result from subgraph
    result: dict

def create_initial_state(user_input: str, thread_id: Optional[str] = None) -> GraphState:
    """Create initial GraphState for a new conversation."""
    return GraphState(
        thread_id=thread_id or str(uuid.uuid4()),
        messages=[HumanMessage(content=user_input)],
        route=None
    )
