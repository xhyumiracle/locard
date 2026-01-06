"""
Single-round tool calling agent wrapper.

Provides a react-agent-like interface for tool calling with structured output.
Unlike react agent (multi-round autonomous tool calling), this agent:
- Makes tool calls in a single round (Phase 1)
- Returns structured output after tool execution (Phase 2)
- Gives orchestrator full control over the workflow
"""

import logging
from typing import List, Any, Dict
from langchain_core.messages import AIMessage, ToolMessage, BaseMessage
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ToolAgent:
    """Single-round tool calling agent with structured output.

    Usage:
        agent = ToolAgent(llm, tools, output_schema)
        result = agent.invoke(messages)

    Similar to react agent but:
    - Only makes tool calls in one round (not autonomous multi-round)
    - Returns structured output after tool execution
    - Orchestrator controls the workflow via messages
    """

    def __init__(
        self,
        llm: BaseChatModel,
        tools: List[BaseTool],
        output_schema: type[BaseModel]
    ):
        """Initialize tool agent.

        Args:
            llm: Base language model
            tools: List of @tool decorated functions
            output_schema: Pydantic model for structured output
        """
        self.llm = llm
        self.tools = tools
        self.output_schema = output_schema

        # Two-phase LLM: with tools (phase 1) and with structured output (phase 2)
        self.llm_with_tools = llm.bind_tools(tools)
        self.llm_with_structure = llm.with_structured_output(output_schema)

    def invoke(self, messages: List[BaseMessage]) -> BaseModel:
        """Invoke agent with messages, return structured output.

        Flow:
        1. Phase 1: LLM decides whether to call tools
        2. If tools called: Execute tools and add results to messages
        3. Phase 2: LLM generates structured output

        Args:
            messages: Input messages for the agent

        Returns:
            Structured output (instance of output_schema)
        """
        # Phase 1: Tool calling (if LLM decides to use tools)
        response = self.llm_with_tools.invoke(messages)

        # Check if tools were called
        if hasattr(response, 'tool_calls') and response.tool_calls:
            logger.info(f"Agent called {len(response.tool_calls)} tool(s)")

            # Add response with tool_calls once
            messages = messages + [response]

            # Execute tools and add results to messages
            for tc in response.tool_calls:
                tool_name = tc['name']
                tool_args = tc['args']
                logger.debug(f"Executing tool: {tool_name} with args: {tool_args}")

                # Find and execute the tool
                tool_result = None
                for tool in self.tools:
                    if tool.name == tool_name:
                        tool_result = tool.invoke(tool_args)
                        break

                if tool_result is None:
                    tool_result = f"Unknown tool: {tool_name}"
                    logger.warning(f"Unknown tool called: {tool_name}")

                logger.debug(f"Tool result: {tool_result}")

                # Add tool result to messages
                messages.append(ToolMessage(
                    content=str(tool_result),
                    tool_call_id=tc['id']
                ))

        # Phase 2: Get structured output (after tool execution or directly)
        result = self.llm_with_structure.invoke(messages)
        return result


def create_tool_agent(
    llm: BaseChatModel,
    tools: List[BaseTool],
    output_schema: type[BaseModel]
) -> ToolAgent:
    """Create a tool agent (factory function for consistency with langgraph API).

    Args:
        llm: Base language model
        tools: List of @tool decorated functions
        output_schema: Pydantic model for structured output

    Returns:
        ToolAgent instance
    """
    return ToolAgent(llm, tools, output_schema)
