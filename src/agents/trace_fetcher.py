"""
Trace Fetcher Agent - Executes blockchain data queries.

Responsibilities:
- Parse task briefs from Orchestrator
- Select and call appropriate blockchain tools
- Handle retries and errors
- Return structured findings
"""

from typing import List, Literal, Optional, Dict, Any
from typing_extensions import TypedDict

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

import config
from src.state.tracetx_state import state_ids_hint, TraceTxState
from src.models.finding import Finding as FindingDict
from src.tools.registry import get_trace_fetcher_tools
from src.tools.state_tools import create_state_lookup_tool
from src.agents.prompts import load_prompt
from src.utils.debug import print_messages, print_structure_output
from src.utils.llm import create_chat_openai_with_retry


# ==================== Structured Output Schema (Pydantic) ====================

class FindingSchema(BaseModel):
    """A single finding (one per tool call)."""
    kind: str = Field(description="tx (single tx fetch), address_txs (address history), search_txs (search/filter outputs/txs), or price")
    tool_name: str = Field(description="Exact function name you called (must match tool call)")
    result_hint: List[str] = Field(
        default_factory=list,
        description="Minimum keywords from tool RESULT (not args) to distinguish this call from others of same tool. "
                    "Only needed if you called the same tool multiple times. Use shortest unique identifiers (e.g., txid prefix)."
    )
    rationale: str = Field(description="Why this finding is relevant")


class FetchReportSchema(BaseModel):
    # task: str = Field(description="Echo of the original task brief")
    findings: List[FindingSchema] = Field(default_factory=list, description="List of all findings")
    gaps: List[str] = Field(default_factory=list, description="Unresolved issues or errors encountered")


# ==================== Agent ====================

class TraceFetcherAgent:
    """Trace Fetcher Agent that executes blockchain queries."""

    def __init__(self):
        self.base_tools = get_trace_fetcher_tools()
        self.llm = create_chat_openai_with_retry(
            model=config.get_agent_model("trace_fetcher"),
            temperature=0
        ).bind(parallel_tool_calls=False)
        self.prompt = load_prompt("trace_fetcher")

    def fetch(self, task_brief: str, state: Optional[TraceTxState] = None) -> dict:
        """
        Execute a task brief and return findings.

        Args:
            task_brief: The task description from Orchestrator
            state: Optional current state for context

        Returns:
            State updates findings and gaps
        """
        # Build tools list (add state_lookup if state available)
        tools = list(self.base_tools)
        if state:
            tools.append(create_state_lookup_tool(state))

        # Create agent with current tools
        agent = create_react_agent(
            self.llm,
            tools,
            prompt=self.prompt,
            response_format=FetchReportSchema
        )

        # Build input with optional state hint
        brief_with_hint = task_brief
        if state:
            hint = state_ids_hint(state)
            if hint:
                brief_with_hint = f"{task_brief}\n\n[Existing IDs: {hint}]"

        input_messages = [HumanMessage(content=brief_with_hint)]

        print_messages("trace_fetcher", "Input", input_messages)

        result = agent.invoke({
            "messages": input_messages
        })

        # Log
        messages = result.get("messages", input_messages)
        print_messages("trace_fetcher", "Output", messages)

        structured: Optional[FetchReportSchema] = result.get("structured_response")
        assert structured is not None, "structured_response not found in agent result"
        print_structure_output("trace_fetcher", structured.model_dump())

        # extract findings with hints
        result = self._schema_to_output(structured, messages)
        return {
            "findings": result["findings"],
            "gaps": result["gaps"]
        }


    def _schema_to_output(self, schema: FetchReportSchema, messages: list) -> dict:
        """Convert FetchReportSchema (Pydantic) to state updates (TypedDict).

        Extracts data from tool messages using tool_name matching.
        Uses result_hint only when same tool called multiple times.
        """
        # Build tool_name -> [results] mapping
        tool_results = self._extract_tool_results(messages)

        findings: List[FindingDict] = []
        gaps: List[str] = list(schema.gaps)  # Start with LLM-reported gaps

        for f in schema.findings:
            # Match by tool_name, use result_hint only if multiple results
            # Returns {"args": {...}, "result": {...}} or None
            entry = self._match_tool_result(tool_results, f.tool_name, f.result_hint)

            if entry is None:
                gaps.append(f"No tool result matched: tool={f.tool_name}, hint={f.result_hint}")
                continue

            # No deduplication - if Fetcher agent is smart, it shouldn't produce duplicate tool calls
            # Removed deduplication logic that was masking upstream issues

            # Extract id from matched entry (uses both args and result)
            finding_id = self._extract_id_from_data(f.kind, entry)

            # Store only result in data field (args used internally for ID extraction)
            findings.append(FindingDict(
                kind=f.kind,
                id=finding_id,
                source=f.tool_name,
                rationale=f.rationale,
                data=entry.get("result", {})
            ))

        return {
            "findings": findings,
            "gaps": gaps
        }

    def _match_tool_result(
        self,
        tool_results: Dict[str, List[Dict[str, Any]]],
        tool_name: str,
        result_hint: List[str]
    ) -> Optional[Dict[str, Any]]:
        """Match finding to tool result by tool_name, using result_hint for disambiguation.

        Each entry in tool_results is {"args": {...}, "result": {...}}.
        Hint matching searches both args and result.

        Strategy:
        1. Find all entries matching tool_name (partial match)
        2. If only one entry, return it (no hint needed)
        3. If multiple entries, use result_hint to distinguish (searches args + result)
        """
        # Collect all entries matching tool_name
        matching_entries: List[Dict[str, Any]] = []
        for name, entries in tool_results.items():
            if tool_name in name or name in tool_name:
                matching_entries.extend(entries)

        if not matching_entries:
            # Fallback: try all entries if tool_name doesn't match
            for entries in tool_results.values():
                matching_entries.extend(entries)

        if not matching_entries:
            return None

        # If only one entry, return it directly (no disambiguation needed)
        if len(matching_entries) == 1:
            return matching_entries[0]

        # Multiple entries: use result_hint to distinguish (search args + result)
        if not result_hint:
            # No hint provided, return first entry
            return matching_entries[0]

        for entry in matching_entries:
            # Build searchable string from both args and result
            args_str = self._flatten_values(entry.get("args", {}))
            result_str = self._flatten_values(entry.get("result", {}))
            combined_str = f"{args_str} {result_str}"
            if all(str(h).lower() in combined_str for h in result_hint):
                return entry

        # No match with hint, return first entry as fallback
        return matching_entries[0]

    def _flatten_values(self, obj: Any, depth: int = 3) -> str:
        """Flatten nested dict/list values into searchable lowercase string."""
        if depth <= 0:
            return str(obj).lower()
        if isinstance(obj, dict):
            parts = []
            for v in obj.values():
                if v is not None:
                    parts.append(self._flatten_values(v, depth - 1))
            return " ".join(parts)
        elif isinstance(obj, list):
            parts = []
            for item in obj[:20]:  # Limit list items
                parts.append(self._flatten_values(item, depth - 1))
            return " ".join(parts)
        else:
            return str(obj).lower()

    def _extract_id_from_data(self, kind: str, entry: Dict[str, Any]) -> str:
        """Extract canonical id from matched entry based on kind.

        Entry structure: {"args": {...}, "result": {...}}
        Uses both args and result to build meaningful IDs.
        """
        args = entry.get("args", {})
        result = entry.get("result", {})

        if kind == "tx":
            # Result may be a list (from get_txs tools) or dict (from get_tx tools)
            if isinstance(result, list):
                if len(result) != 1:
                    raise ValueError(f"kind='tx' expects single tx, got {len(result)} txs. Use 'search_txs' or 'address_txs' for multiple results.")
                return result[0]["txid"]
            return result["txid"]
        # elif kind in ("address", "address_txs"):
        #     # Address may be in result or args depending on tool
        #     # Result may be a list of txs
        #     if isinstance(result, list) and result:
        #         chain = args.get("chain") or result[0].get("chain")
        #     else:
        #         chain = args.get("chain") or result.get("chain")
        #     addr = args.get("address")
        #     return f"{chain}-{addr}"
        elif kind == "price":
            # Build id: COIN_in_QUOTE means "price of 1 COIN in QUOTE units"
            coin = args["coin"]
            quote = args["quote"]
            start_ts = args.get("start_time")
            end_ts = args.get("end_time")
            return f"{coin}_in_{quote}@time({start_ts}-{end_ts})"
        elif kind == "search_txs":
            # Use time window from args
            # Result may be a list of txs
            if isinstance(result, list) and result:
                chain = args.get("chain") or result[0].get("chain")
            else:
                chain = args.get("chain") or result.get("chain")
            start_ts = args.get("min_timestamp")
            end_ts = args.get("max_timestamp")
            return f"{chain}@{start_ts}-{end_ts}"
        raise ValueError(f"Unknown finding kind: {kind}")

    def _extract_tool_results(self, messages: list) -> Dict[str, List[Dict[str, Any]]]:
        """Extract tool results from message history. Returns tool_name -> [{args, result}].

        Each entry contains:
        - args: tool call arguments (from AI message)
        - result: tool return value (from tool message)

        Handles both single dict and list returns from tools.
        For list returns (e.g., get_txs, search_txs), each item becomes a separate result.
        """
        import json
        import ast

        # First pass: build tool_call_id -> args mapping from AI messages
        tool_call_args: Dict[str, Dict[str, Any]] = {}
        for msg in messages:
            if getattr(msg, 'type', None) != 'ai':
                continue
            tool_calls = getattr(msg, 'tool_calls', None)
            if not tool_calls:
                continue
            for tc in tool_calls:
                if isinstance(tc, dict):
                    tc_id = tc.get('id')
                    tc_args = tc.get('args', {})
                else:
                    tc_id = getattr(tc, 'id', None)
                    tc_args = getattr(tc, 'args', {})
                if tc_id:
                    tool_call_args[tc_id] = tc_args

        # Second pass: extract tool results and pair with args
        tool_results: Dict[str, List[Dict[str, Any]]] = {}

        for msg in messages:
            if getattr(msg, 'type', None) != 'tool':
                continue

            tool_name = getattr(msg, 'name', 'unknown')
            tool_call_id = getattr(msg, 'tool_call_id', None)
            content = getattr(msg, 'content', None)
            parsed = None

            if content:
                if isinstance(content, (dict, list)):
                    parsed = content
                elif hasattr(content, 'model_dump'):
                    parsed = content.model_dump()
                elif isinstance(content, str):
                    try:
                        parsed = json.loads(content)
                    except json.JSONDecodeError:
                        try:
                            parsed = ast.literal_eval(content)
                        except (ValueError, SyntaxError):
                            parsed = {"raw": content}

            if parsed:
                if tool_name not in tool_results:
                    tool_results[tool_name] = []

                # Get args for this tool call
                args = tool_call_args.get(tool_call_id, {})

                # Keep list results as-is (one tool call = one entry)
                # Don't split lists - search tools return multiple items as one result
                tool_results[tool_name].append({"args": args, "result": parsed})

        return tool_results
