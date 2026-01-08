"""
Tool Agent with error handling - wraps ToolAgent to catch and report tool errors.

This is a thin wrapper around ToolAgent that catches exceptions from tool calls
and converts them to error messages, allowing the LLM to see the error and proceed.
"""

import logging
from typing import List
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_core.messages import ToolMessage
from pydantic import BaseModel

from src.agents.tool_agent import ToolAgent

logger = logging.getLogger(__name__)


class ToolAgentWithErrorHandling(ToolAgent):
    """Tool Agent that catches tool exceptions and converts them to error messages."""

    def invoke(self, messages: List) -> BaseModel:
        """Invoke agent with messages, return structured output.

        Tool errors are caught and converted to error messages instead of propagating.
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
                        try:
                            tool_result = tool.invoke(tool_args)
                        except Exception as e:
                            # Convert exception to error message
                            tool_result = f"Error: {type(e).__name__}: {str(e)}"
                            logger.warning(f"Tool {tool_name} raised exception: {e}")
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


def create_tool_agent_with_error_handling(
    llm: BaseChatModel,
    tools: List[BaseTool],
    output_schema: type[BaseModel]
) -> ToolAgentWithErrorHandling:
    """Create a tool agent with error handling.

    Tool exceptions will be caught and converted to error messages that the LLM can see.

    Args:
        llm: Base language model
        tools: List of @tool decorated functions
        output_schema: Pydantic model for structured output

    Returns:
        ToolAgentWithErrorHandling instance
    """
    return ToolAgentWithErrorHandling(llm, tools, output_schema)
