"""
Trace Fetcher Agent - Executes blockchain data queries.

Responsibilities:
- Parse task briefs from Orchestrator
- Select and call appropriate blockchain tools
- Handle retries and errors
- Return structured findings
"""

import logging
from typing import List, Optional, Dict, Any, Literal

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field, ConfigDict

import config
from src.state.tracetx_state import state_ids_hint, TraceTxState
from src.models.finding import Finding as FindingDict, build_finding_id, get_finding_kinds_hint
from src.tools.registry import get_trace_fetcher_tools
from src.tools.state_tools import create_state_lookup_tool
from src.prompts import load_prompt
from src.utils.debug import print_messages, print_structure_output
from src.llm import create_chat_model
from src.utils.string import is_numeric_like


# ==================== Structured Output Schema (Pydantic) ====================

class FindingSchema(BaseModel):
    """A single finding (one per tool call)."""
    model_config = ConfigDict(extra='forbid')

    kind: Literal["get_tx", "price", "search_txs"] = Field(
        description="Finding kind. Choose based on query method:\n"
                    "- get_tx: Direct fetch BY tx hash(es)\n"
                    "- price: Price data query\n"
                    "- search_txs: Search/filter txs by conditions"
    )
    tool_name: str = Field(
        description="Exact TOOL NAME you called (must match tool call). "
                    "INVALID: state_lookup, or any string containing ':'"
    )
    tool_args_hint: List[str] = Field(
        default_factory=list,
        description="Extract VALUES from YOUR tool call args (NOT task brief). "
                    "Examples: ['1700001234', '1700005678'] for timestamps, ['BTC', 'ETH'] for coins. "
                    "ALL VALUES should be exactly one of your actual tool call args"
                    "DO NOT include any words from task brief, NO 'out', NO 'direction'"
    )


class FetchReportSchema(BaseModel):
    model_config = ConfigDict(extra='forbid')

    # task: str = Field(description="Echo of the original task brief")
    findings: List[FindingSchema] = Field(default_factory=list, description="List of all findings")
    gaps: List[str] = Field(default_factory=list, description="Stop reason when failed to provide any findings")


# ==================== Agent ====================

logger = logging.getLogger(__name__)


class TraceFetcherAgent:
    """Trace Fetcher Agent that executes blockchain queries."""

    def __init__(self):
        self.base_tools = get_trace_fetcher_tools()
        self.llm = create_chat_model(
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
        # Build tools list
        tools = list(self.base_tools)

        # NOTE: NO STATE_LOOKUP for now, let LLM decide what to fetch
        # if state:
        #     tools.append(create_state_lookup_tool(state))

        # Create agent with current tools
        # Tuple format: (system_prompt_for_structured_response, schema)
        # This prompt is ONLY used in the final structured response generation call
        # to suppress verbose text and save output tokens (4x more expensive than input)
        agent = create_react_agent(
            self.llm,
            tools,
            prompt=self.prompt,
            response_format=(
                "CRITICAL INSTRUCTION: Output ONLY the raw JSON object, nothing else. "
                "STRICTLY FORBIDDEN: Any text before/after JSON, markdown (```json), code blocks, explanations, formatting, whitespace. "
                "REQUIRED FORMAT: Single-line compact JSON exactly matching schema. "
                "VIOLATION = FAILURE.",
                FetchReportSchema
            )
        )

        # Build input with optional state hint
        # NOTE: NO HINT for now, let LLM decide what to fetch
        brief_with_hint = task_brief
        # if state:
        #     hint = state_ids_hint(state)
        #     if hint:
        #         brief_with_hint = f"{task_brief}\n\n[Existing IDs: {hint}]"

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
        seen_ids: set = set()  # Track seen finding IDs for deduplication

        # Detect potential LLM hallucination: gaps reported but no tool calls made
        # Can't distinguish no fingins vs no tool call
        # if schema.gaps and not tool_results:
        #     logger.warning(
        #         "LLM reported gaps without calling any tools - possible hallucination. "
        #         f"Gaps: {schema.gaps}"
        #     )
        #     gaps.append("WARNING: LLM refused to call tools (possible hallucination)")

        for f in schema.findings:
            # Validate tool_name before matching
            if ":" in f.tool_name:
                raise ValueError(f"Invalid tool_name '{f.tool_name}': contains ':' (looks like an ID, not a tool name)")

            if f.tool_name == "state_lookup":
                logger.warning(f"Finding uses state_lookup instead of fetch tool. Skipping. Use fetch tools to get new data.")
                gaps.append(f"Used state_lookup instead of fetch tool (invalid)")
                continue

            # Match by tool_name + args_hint (fuzzy match allowed)
            # Returns list of matching entries (can be 0, 1, or multiple)
            matched_entries = self._match_tool_result(tool_results, f.tool_name, f.tool_args_hint)

            if not matched_entries:
                # Tool executed but returned no results (e.g., empty search)
                # Log warning and add gap, but don't crash - orchestrator can handle it
                warning_msg = f"No tool result matched: tool={f.tool_name}, hints={f.tool_args_hint}"
                logger.warning(
                    f"Finding matching failed: {warning_msg}\n"
                    f"Available tools: {list(tool_results.keys())}\n"
                    f"This usually means the tool returned empty results (no candidates found)."
                )
                gaps.append(f"NOT_FOUND: {f.tool_name} returned no results for hints={f.tool_args_hint}")
                # Skip this finding (don't add to results) and continue processing others
                continue

            # Process all matched entries (deduplication happens at finding_id level)
            for entry in matched_entries:
                # Extract id from matched entry (uses both args and result)
                finding_id = self._build_id_from_tool_call_data(f.kind, entry)

                # Deduplicate by ID - skip if we've already added this finding
                if finding_id in seen_ids:
                    logger.info(
                        f"Skipping duplicate finding: kind={f.kind}, tool={f.tool_name}, "
                        f"id={finding_id}, hints={f.tool_args_hint}"
                    )
                    continue

                seen_ids.add(finding_id)

                # Store only result in data field (args used internally for ID extraction)
                findings.append(FindingDict(
                    kind=f.kind,
                    id=finding_id,
                    source=f.tool_name,
                    rationale="",  # Removed: was causing LLM to generate unnecessary summaries
                    data=entry.get("result", {})
                ))

        # If we have any valid findings, clear gaps to avoid confusion
        # Gaps should only be reported when there's complete failure (no findings at all)
        if findings:
            if gaps:
                logger.info(f"Clearing {len(gaps)} gaps because we have {len(findings)} valid findings")
            gaps = []

        return {
            "findings": findings,
            "gaps": gaps
        }

    def _args_match(self, hints: List[str], entry: Dict[str, Any]) -> bool:
        """Check if hints match tool call entry (args + result).

        Smart matching strategy:
        1. Separate hints into numeric and non-numeric
        2. All numeric hints MUST match (they're critical identifiers)
        3. Non-numeric hints are optional if numeric hints exist

        Args:
            hints: List of hint strings from LLM
            entry: Tool call entry with {"args": {...}, "result": {...}}

        Returns:
            True if hints match according to smart rules
        """
        if not hints:
            return True

        # Flatten both args and result for searching
        args_str = self._flatten_values(entry.get("args", {}))
        result_str = self._flatten_values(entry.get("result", {}))
        combined = f"{args_str} {result_str}"

        # Classify hints into numeric and non-numeric
        numeric_hints = [h for h in hints if is_numeric_like(h)]
        non_numeric_hints = [h for h in hints if not is_numeric_like(h)]

        # Rule 1: All numeric hints must match (they're critical)
        for hint in numeric_hints:
            hint_lower = str(hint).lower().strip()
            if hint_lower not in combined:
                return False

        # Rule 2: Non-numeric hints - flexible based on whether we have numeric hints
        if non_numeric_hints:
            if numeric_hints:
                # Have numeric identifiers - non-numeric are optional (may be from task brief)
                # Just log if they don't match but don't fail
                for hint in non_numeric_hints:
                    hint_lower = str(hint).lower().strip()
                    if hint_lower and hint_lower not in combined:
                        logger.debug(f"Non-numeric hint '{hint}' not found but ignored (have numeric hints)")
            else:
                # No numeric hints - need at least one non-numeric to match
                matched_any = False
                for hint in non_numeric_hints:
                    hint_lower = str(hint).lower().strip()
                    if hint_lower and hint_lower in combined:
                        matched_any = True
                        break
                if not matched_any:
                    return False

        return True

    def _match_tool_result(
        self,
        tool_results: Dict[str, List[Dict[str, Any]]],
        tool_name: str,
        tool_args_hint: List[str]
    ) -> List[Dict[str, Any]]:
        """Match finding to tool results by tool_name + args_hint with fallback.

        Smart matching strategy with LLM error tolerance:
        1. Try matching by tool_name (partial match)
        2. If no match and has args_hint, fallback to match all tools by args
        3. If only 1 match, return immediately (no need to use hints)
        4. If multiple matches, filter by args_hint

        Args:
            tool_results: Dict mapping tool names to list of call records
            tool_name: Tool name from LLM finding (may be wrong)
            tool_args_hint: List of hint strings from LLM (arg values to search for)

        Returns:
            List of matching entries (can be empty)
        """
        # Step 1: Try matching by tool_name (partial match)
        matching_entries: List[Dict[str, Any]] = []
        for name, entries in tool_results.items():
            if tool_name in name or name in tool_name:
                matching_entries.extend(entries)

        # Step 2: If tool_name didn't match but we have args_hint, try fallback
        if not matching_entries and tool_args_hint:
            logger.info(f"Tool name '{tool_name}' not matched, trying args_hint fallback")
            for entries in tool_results.values():
                matching_entries.extend(entries)

        if not matching_entries:
            return []

        # Step 3: Single match - return immediately (no need to distinguish)
        if len(matching_entries) == 1:
            return matching_entries

        # Step 4: Multiple matches - filter by args_hint
        if not tool_args_hint:
            logger.warning(
                f"Multiple tool calls ({len(matching_entries)}) but no hints provided - "
                f"returning all (may cause duplicates)"
            )
            return matching_entries

        matched = []
        for entry in matching_entries:
            if self._args_match(tool_args_hint, entry):
                matched.append(entry)

        return matched

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

    def _build_id_from_tool_call_data(self, kind: str, entry: Dict[str, Any]) -> str:
        """Extract canonical id from matched entry based on kind.

        Entry structure: {"args": {...}, "result": {...}}
        Uses both args and result to build meaningful IDs.

        This method maps tool results to finding ID spec fields.
        """
        args = entry.get("args", {})
        result = entry.get("result", {})

        # Map tool result to finding ID spec fields
        if kind == "get_tx":
            # Result may be a list (from get_txs tools) or dict (from get_tx tools)
            # Collect all txids (single or batch)
            txids = []
            if isinstance(result, list):
                txids = [tx["txid"] for tx in result if "txid" in tx]
            else:
                if "txid" in result:
                    txids = [result["txid"]]

            if not txids:
                raise ValueError(f"kind='get_tx' requires at least one txid in result")

            return build_finding_id("get_tx", txids=txids)

        elif kind == "price":
            return build_finding_id("price",
                coin=args["coin"],
                quote=args["quote"],
                start_ts=args.get("start_ts"),
                end_ts=args.get("end_ts")
            )

        elif kind == "search_txs":
            # Extract chain from args or result
            if isinstance(result, list) and result:
                chain = args.get("chain") or result[0].get("chain")
            else:
                chain = args.get("chain") or result.get("chain")

            return build_finding_id("search_txs",
                chain=chain,
                min_timestamp=args.get("min_timestamp"),
                max_timestamp=args.get("max_timestamp")
            )

        else:
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
