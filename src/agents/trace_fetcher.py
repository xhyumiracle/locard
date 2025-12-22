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

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

import config
from src.tools.registry import get_trace_fetcher_tools
from src.state.graph_state import GraphState, create_error_event


class SourceRef(TypedDict, total=False):
    source: str       # e.g. "blockcypher" / "electrs"
    endpoint: str     # e.g. "get_transaction"
    params: str       # e.g. "tx=0x..."


class Finding(TypedDict):
    kind: Literal["tx", "event", "address", "address_txs", "search_txs", "price"]
    id: str           # txhash / event-id / address / address:Ntxs / search:Ntxs / price-query-key
    rationale: str    # 1-line explanation
    data: Dict[str, Any]  # raw tool response data


class FetchReport(TypedDict):
    task: str               # echoed task brief
    findings: List[Finding] # best-first, top-k
    gaps: List[str]         # optional, unresolved issues


TRACE_FETCHER_SYSTEM_PROMPT = """You are the Trace Fetcher Agent. You act as an autonomous investigator that uses blockchain data tools to gather evidence in response to a task brief from the Orchestrator.

## Your Responsibilities
1) Parse the task_brief to understand what evidence is needed.
2) Select appropriate blockchain data tool(s) and construct queries.
3) Execute tool calls; the retry logic is handled automatically.
4) Normalize raw API responses into structured findings.
5) Return a FetchReport with findings and any gaps.

## Available Tools
You have access to:
- get_btc_transaction_mempool(tx_hash): Get Bitcoin transaction details (via Mempool.space, FREE - PREFER THIS)
- get_btc_address_info_mempool(address): Get Bitcoin address balance/stats (via Mempool.space, FREE - PREFER THIS)
- get_btc_address_txs_mempool(address, limit, min_timestamp, max_timestamp): Get Bitcoin address transaction history with optional time filter (FREE)
- get_btc_transaction(tx_hash): Get Bitcoin transaction details (via BlockCypher, rate limited)
- get_doge_transaction_electrs(tx_hash): Get Dogecoin transaction (via Electrs, FREE - PREFER THIS)
- get_doge_address_info_electrs(address): Get Dogecoin address balance/stats (via Electrs, FREE - PREFER THIS)
- get_doge_address_txs_electrs(address, limit, min_timestamp, max_timestamp): Get Dogecoin address transaction history with optional time filter (FREE)
- search_doge_txs_by_time(min_timestamp, max_timestamp, min_amount_doge, max_amount_doge, limit, max_blocks): Search DOGE transactions by time window and amount range (FREE, scans blocks)
- get_doge_transaction(tx_hash): Get Dogecoin transaction details (via BlockCypher, rate limited)
- get_btc_address_info(address): Get Bitcoin address balance/stats (via BlockCypher, rate limited)
- get_doge_address_info(address): Get Dogecoin address balance/stats (via BlockCypher, rate limited)
- get_historical_price(coin, quote, timestamp): Get historical cryptocurrency price

IMPORTANT: Always prefer the FREE tools (mempool, electrs) over BlockCypher to avoid rate limits.

## Task Brief Mapping
When you receive a task brief, you MUST make a tool call. Map the task to tools as follows:
- "Fetch BTC transaction <hash>" → get_btc_transaction_mempool(tx_hash=<hash>)
- "Fetch DOGE transaction <hash>" → get_doge_transaction_electrs(tx_hash=<hash>)
- "Fetch BTC address <addr> info" → get_btc_address_info_mempool(address=<addr>)
- "Fetch DOGE address <addr> info" → get_doge_address_info_electrs(address=<addr>)
- "Fetch BTC address <addr> txs from <min_ts> to <max_ts>" → get_btc_address_txs_mempool(address=<addr>, min_timestamp=<min_ts>, max_timestamp=<max_ts>)
- "Fetch DOGE address <addr> txs from <min_ts> to <max_ts>" → get_doge_address_txs_electrs(address=<addr>, min_timestamp=<min_ts>, max_timestamp=<max_ts>)
- "Search DOGE txs from <min_ts> to <max_ts> with amount <min_amt> to <max_amt>" → search_doge_txs_by_time(min_timestamp=<min_ts>, max_timestamp=<max_ts>, min_amount_doge=<min_amt>, max_amount_doge=<max_amt>)
- "Fetch DOGE/BTC price at timestamp <ts>" → get_historical_price(coin="DOGE", quote="BTC", timestamp=<ts>)
- "Fetch DOGE/USDT price at timestamp <ts>" → get_historical_price(coin="DOGE", quote="USDT", timestamp=<ts>)
- "Fetch BTC/USDT price at timestamp <ts>" → get_historical_price(coin="BTC", quote="USDT", timestamp=<ts>)
- "Fetch <COIN1>/<COIN2> price at timestamp <ts>" → get_historical_price(coin="<COIN1>", quote="<COIN2>", timestamp=<ts>)

CRITICAL RULES:
1. You MUST make at least one tool call for FETCH tasks
2. NEVER skip a tool call - always attempt it
3. The price tool handles symbol ordering automatically (e.g., DOGE/BTC will work even if only DOGEBTC exists)
4. Let the tool fail if there's an issue - don't preemptively decide not to call it
5. If the task starts with "Calculate", "Analyze", "Find matching", or asks you to do reasoning:
   - DO NOT call any tool
   - Report a gap: "This task requires analysis/calculation, not a fetch operation. The Orchestrator should handle this."

## Principles
- Return only top-k most relevant hits (default k ≤ 5)
- Each finding must include reproducible evidence (source, endpoint, params)
- Normalize amounts to smallest units (satoshi for BTC, koinu for DOGE)
- Use chain identifiers: "BTC", "DOGE", "ETH"
- Do not make judgments about cross-chain links; only report raw findings
- If a tool fails, report it in gaps rather than guessing

## CRITICAL: Never Fabricate Data
- NEVER make up, guess, or fabricate transaction hashes, addresses, or any other parameters
- NEVER use placeholder values like "sample_tx_hash", "some_address", "example_hash", etc.
- If you don't have a real transaction hash or address, DO NOT call the tool
- Instead, report in gaps that you need specific data to proceed
- Only call tools with REAL values extracted from the task brief or previous findings

## Response Format
Always structure your final response as a FetchReport with:
- task: The task brief you received
- findings: List of findings with kind, id, rationale, and data
- gaps: Any issues or missing information"""


class TraceFetcherAgent:
    """Trace Fetcher Agent that executes blockchain queries."""

    def __init__(self):
        self.tools = get_trace_fetcher_tools()
        self.llm = ChatOpenAI(
            model=config.LLM_MODEL,
            temperature=0,  # Deterministic for tool calling
            max_tokens=config.LLM_MAX_TOKENS
        )

        # Create react agent with tools
        self.agent = create_react_agent(
            self.llm,
            self.tools,
            prompt=TRACE_FETCHER_SYSTEM_PROMPT
        )

    def fetch(self, task_brief: str, state: Optional[GraphState] = None) -> FetchReport:
        """
        Execute a task brief and return findings.

        Args:
            task_brief: The task description from Orchestrator
            state: Optional current state for context

        Returns:
            FetchReport with findings and gaps
        """
        try:
            # React agent expects messages input
            result = self.agent.invoke({
                "messages": [HumanMessage(content=task_brief)]
            })

            # Parse the agent's output into FetchReport format
            return self._parse_agent_output(task_brief, result)

        except Exception as e:
            return FetchReport(
                task=task_brief,
                findings=[],
                gaps=[f"Agent execution failed: {str(e)}"]
            )

    def _parse_agent_output(self, task_brief: str, result: dict) -> FetchReport:
        """Parse react agent output into FetchReport."""
        findings: List[Finding] = []
        gaps: List[str] = []

        messages = result.get("messages", [])

        # Process messages to extract tool results
        for msg in messages:
            msg_type = getattr(msg, "type", None)

            # Check for tool messages (responses from tool calls)
            if msg_type == "tool":
                tool_name = getattr(msg, "name", "unknown")
                try:
                    content = msg.content
                    if isinstance(content, str):
                        # Try JSON first, then Python literal eval
                        import json
                        import ast
                        try:
                            content = json.loads(content)
                        except json.JSONDecodeError:
                            try:
                                content = ast.literal_eval(content)
                            except (ValueError, SyntaxError):
                                content = {"raw": content}

                    if isinstance(content, dict):
                        if content.get("success"):
                            kind = self._infer_finding_kind(tool_name)
                            finding_id = self._extract_finding_id(content, kind)
                            finding = Finding(
                                kind=kind,
                                id=finding_id,
                                rationale=f"Retrieved via {tool_name}",
                                data=content
                            )
                            findings.append(finding)
                        else:
                            gaps.append(f"{tool_name}: {content.get('error', 'unknown error')}")
                except Exception as e:
                    gaps.append(f"Error parsing {tool_name} result: {e}")

            # Also check for AI messages with tool_calls (some LangGraph versions)
            elif msg_type == "ai" and hasattr(msg, "tool_calls") and msg.tool_calls:
                # This is an AI message that requested tool calls
                pass  # The tool response will come in subsequent messages

        # If no tool findings at all, report as a gap
        if not findings:
            gaps.append("No successful tool calls completed for this task")

        return FetchReport(
            task=task_brief,
            findings=findings,
            gaps=gaps
        )

    def _infer_finding_kind(self, tool_name: str) -> Literal["tx", "event", "address", "address_txs", "search_txs", "price"]:
        """Infer finding kind from tool name."""
        lower = tool_name.lower()
        if "price" in lower or "historical" in lower:
            return "price"
        # Check for search_txs (block scanning search)
        if "search" in lower and "txs" in lower:
            return "search_txs"
        # Check for address_txs BEFORE tx (more specific patterns first)
        if "address_txs" in lower or ("address" in lower and "txs" in lower):
            return "address_txs"
        # Single transaction (not txs plural)
        if "transaction" in lower or ("tx" in lower and "txs" not in lower):
            return "tx"
        if "address" in lower:
            return "address"
        return "tx"

    def _extract_finding_id(self, content: dict, kind: str) -> str:
        """Extract appropriate ID based on finding kind."""
        if kind == "tx":
            return content.get("txid", "unknown")
        elif kind == "address":
            return content.get("address", "unknown")
        elif kind == "address_txs":
            # For address txs list, use address + tx count
            addr = content.get("address", "?")
            tx_count = content.get("tx_count", 0)
            return f"{addr}:{tx_count}txs"
        elif kind == "search_txs":
            # For search results, use time window + tx count
            time_window = content.get("time_window", "?")
            tx_count = content.get("tx_count", 0)
            return f"search:{time_window}:{tx_count}txs"
        elif kind == "price":
            # For price findings, create a descriptive ID
            coin = content.get("coin", "?")
            quote = content.get("quote", "?")
            ts = content.get("timestamp", "?")
            return f"{coin}/{quote}@{ts}"
        return "unknown"


def direct_fetch_transaction(chain: str, tx_hash: str) -> Dict[str, Any]:
    """
    Directly fetch a transaction without LLM.

    Useful for deterministic fetches where we know exactly what to get.

    Args:
        chain: Chain identifier (BTC, DOGE, ETH)
        tx_hash: Transaction hash

    Returns:
        Tool result dict
    """
    from src.tools.blockcypher import get_btc_transaction, get_doge_transaction
    from src.tools.electrs import get_doge_transaction_electrs

    chain = chain.upper()

    if chain == "BTC":
        return get_btc_transaction.invoke({"tx_hash": tx_hash})
    elif chain == "DOGE":
        # Try Electrs first (free), fallback to BlockCypher
        result = get_doge_transaction_electrs.invoke({"tx_hash": tx_hash})
        if not result.get("success"):
            result = get_doge_transaction.invoke({"tx_hash": tx_hash})
        return result
    else:
        return {"success": False, "error": f"Unsupported chain: {chain}"}


def direct_fetch_price(coin: str, timestamp: int) -> Dict[str, Any]:
    """
    Directly fetch price at timestamp without LLM.

    Args:
        coin: Coin symbol (BTC, DOGE, ETH)
        timestamp: Unix seconds

    Returns:
        Price result dict
    """
    from src.tools.binance import get_historical_price
    return get_historical_price.invoke({"coin": coin, "timestamp": timestamp})
