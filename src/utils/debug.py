"""
Debug utilities for BlockchainMAS.

Provides verbose logging for agent input/output to help with debugging.

Verbosity levels:
  -v  (level 1): Log agent messages at INFO level
  -vv (level 2): Log detailed state at DEBUG level
"""

import json
import logging
from typing import List, Any, Dict, Optional

logger = logging.getLogger(__name__)

# Cache system prompts at module initialization (content -> prompt name)
_SYSTEM_PROMPTS: Dict[str, str] = {}

def _load_system_prompts():
    """Load all system prompts once at module initialization."""
    from src.prompts.loader import load_prompt, PROMPTS_DIR

    if not PROMPTS_DIR.exists():
        return

    for prompt_file in PROMPTS_DIR.glob("*.md"):
        try:
            name = prompt_file.stem
            content = load_prompt(name)  # Use loader to benefit from lru_cache
            _SYSTEM_PROMPTS[content] = name
        except Exception:
            pass

# Initialize once on module load
_load_system_prompts()


def _get_prompt_name(content: str) -> Optional[str]:
    """Check if content is a system prompt and return its name."""
    return _SYSTEM_PROMPTS.get(content.strip())


def _format_messages(messages: list, max_len: int = None) -> str:
    """Format messages list for clean output, including tool calls."""
    if not messages:
        return "  (no messages)"

    lines = []
    for m in messages:
        # Handle both LangChain message objects and dicts
        if isinstance(m, dict):
            content = m.get("content", str(m))
            msg_type = m.get("role", "unknown")
            tool_calls = m.get("tool_calls", [])
            tool_name = None
        else:
            content = getattr(m, "content", str(m))
            msg_type = getattr(m, "type", type(m).__name__)
            tool_calls = getattr(m, "tool_calls", [])
            tool_name = getattr(m, "name", None)  # For ToolMessage

        # For ToolMessage, show the tool name and tool_call_id
        tool_call_id = getattr(m, "tool_call_id", None) if not isinstance(m, dict) else m.get("tool_call_id")
        if msg_type == "tool" and tool_name:
            msg_type = f"tool:{tool_name}"
            if tool_call_id:
                msg_type = f"tool:{tool_name}[{tool_call_id}]"

        # Check if this is a system prompt and abbreviate it
        if isinstance(content, str):
            prompt_name = _get_prompt_name(content)
            if prompt_name:
                # Replace full prompt with abbreviated reference
                content = f"<System Prompt: {prompt_name}.md>"
            else:
                # Indent multiline content for non-prompts
                content_lines = content.split("\n")
                if len(content_lines) > 1:
                    content = content_lines[0] + "\n" + "\n".join("    " + l for l in content_lines[1:])

        lines.append(f"  [{msg_type}] {content}")

        # Show tool calls if present (AIMessage requesting tool use)
        if tool_calls:
            for tc in tool_calls:
                if isinstance(tc, dict):
                    tc_name = tc.get("name", "?")
                    tc_args = tc.get("args", {})
                    tc_id = tc.get("id", "")
                else:
                    tc_name = getattr(tc, "name", "?")
                    tc_args = getattr(tc, "args", {})
                    tc_id = getattr(tc, "id", "")
                # Show full args - no truncation for debug
                args_str = str(tc_args)
                id_str = f"[{tc_id}]" if tc_id else ""
                lines.append(f"    -> tool_call{id_str}: {tc_name}({args_str})")

    return "\n".join(lines)


def format_label(label: str, pad_char: str = '=', length: int = 60) -> str:
    """Format a centered label with padding characters."""
    if not label:
        return pad_char * length
    # Calculate padding on each side
    label_len = len(label)
    total_padding = length - label_len
    left_padding = total_padding // 2
    right_padding = total_padding - left_padding
    return f"{pad_char * left_padding}{label}{pad_char * right_padding}"


def print_messages(node_name: str, section: str, messages: List[Any] = None):
    """
    Log messages for debugging.

    Args:
        node_name: Name of the node (e.g., "router", "trace_orchestrator")
        section: e.g. "Agent Output" or "Agent Input"
        messages: Optional full message history (shows tool calls in execution order)
    """
    _m = f"[{node_name}] {section}"
    logger.debug(f"\n{format_label(_m, '-', 60)}")

    if messages:
        logger.debug(_format_messages(messages))
        logger.debug("")

    logger.debug(f"{'-'*60}\n")
    
def print_structure_output(node_name: str, output: Any):
    """
    Log structured output for debugging.

    Args:
        node_name: Name of the node (e.g., "router", "trace_orchestrator")
        output: Agent output (structured or raw)
    """
    if output is None:
        return

    _m = f"[{node_name}] Structured Output"
    logger.debug(f"\n{format_label(_m, '-', 60)}")

    if isinstance(output, dict):
        for k, v in output.items():
            logger.debug(f"  {k}: {v}")
    else:
        logger.debug(f"  {output}")
    logger.debug(f"{'-'*60}\n")



def _format_state_full(state: dict, max_len: int = None) -> str:
    """Format full state dict for debug output (no truncation)."""
    result = {}
    for k, v in state.items():
        if k == "messages":
            msgs = []
            for m in v if v else []:
                content = getattr(m, "content", str(m))
                # No truncation for debug
                msg_type = getattr(m, "type", type(m).__name__)
                msgs.append(f"[{msg_type}] {content}")
            result[k] = msgs
        elif isinstance(v, dict):
            result[k] = _format_state_full(v, max_len)
        else:
            result[k] = v
    return json.dumps(result, indent=2, default=str, ensure_ascii=False)
