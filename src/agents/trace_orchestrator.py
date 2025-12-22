"""
Trace Orchestrator Agent - Controls the blockchain tracing workflow.

Responsibilities:
- Interpret user objectives and current blockchain state
- Manage execution plan
- Issue task briefs to Trace Fetcher
- Process fetch reports and identify cross-chain links
- Decide when to continue or stop
"""

from typing import List, Literal, Optional
from typing_extensions import TypedDict

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

import config
from src.state.graph_state import GraphState, PlanStep, Plan, create_error_event
from src.models.core import CrossChainLink, OpRef, Transfer


class TaskWant(TypedDict, total=False):
    k: int                                    # top-k hits desired
    kinds: List[Literal["tx", "event", "address"]]


class TraceOrchestratorOutput(TypedDict, total=False):
    action: Literal["continue", "stop"]
    # if continue
    task_brief: Optional[str]
    want: Optional[TaskWant]
    # if stop
    answer_text: Optional[str]


TRACE_ORCHESTRATOR_SYSTEM_PROMPT = """You are the Blockchain Trace Orchestrator Agent. You control the static tracing workflow for blockchain forensics and attribution tasks. You do not call external tools directly; instead, you issue task briefs to the Trace Fetcher Agent and reason over the returned evidence.

## Your Responsibilities
1) Interpret the user objective and current blockchain state (existing transfers and cclinks).
2) Manage the execution plan (track progress, decide next steps).
3) Produce a clear, ATOMIC task_brief for the Trace Fetcher.
4) Receive FetchReport from Fetcher, analyze findings YOURSELF.
5) Score and evaluate cross-chain link candidates YOURSELF based on evidence.
6) Decide to continue (issue next task) or stop (return final answer).

## CRITICAL: Task Decomposition Rules
Each task_brief must be a FETCH operation. The Fetcher can ONLY call external tools.

WRONG task_brief examples (DO NOT USE):
- "Calculate the equivalent DOGE amount" ← Fetcher cannot calculate
- "Analyze the transaction" ← Fetcher cannot analyze
- "Find matching DOGE transactions" ← Fetcher cannot search without specific identifiers

CORRECT task_brief examples (ALWAYS USE):
- "Fetch BTC transaction <hash>"
- "Fetch DOGE/BTC price at timestamp <ts>"
- "Fetch DOGE address <specific_address> info"

The Fetcher can ONLY fetch. YOU (Orchestrator) MUST:
1. Do all calculations using data from accumulated findings
2. Do all analysis and reasoning
3. Recognize when you cannot proceed (e.g., no specific DOGE address to query)

After getting price data, YOU calculate: BTC_amount / DOGE_BTC_price = estimated_DOGE_amount

## Cross-Chain Tracing Sequence
When tracing from Chain B (e.g., BTC) back to Chain A (e.g., DOGE):
1. Fetch target tx on Chain B → get amount, timestamp, addresses
2. Fetch price data (A/B rate) at that timestamp
3. Calculate expected amount on Chain A (YOU do this calculation)
4. If you have a specific DOGE address to investigate:
   - Calculate time window: (BTC_timestamp - 1800) to BTC_timestamp (30 minutes before)
   - Fetch DOGE address txs with this time filter
   - Look for tx with sent_doge close to your calculated expected amount
5. If you have a specific DOGE tx hash, fetch it directly
6. If no address/tx available, acknowledge limitation

## Task Brief Examples (ATOMIC)
- "Fetch BTC transaction 971e6be13cc2a4aa6f4dcbee48d8d286fec30245d4e7f21597585981b0c7a511"
- "Fetch DOGE/BTC price at timestamp 1609459200"
- "Fetch DOGE address D7example1234567890abcdefghijklmnop info"
- "Fetch DOGE address D7example1234567890abcdefghijklmnop txs from 1609457400 to 1609459200" (with address)
- "Search DOGE txs from 1609457400 to 1609459200 with amount 500 to 700" (without address, by amount range)
- "Fetch DOGE transaction 6e1c362a859e28ac861c97ea17076afb1df71a8d52f08237b1a77a82362ac260"

## When to Stop (with answer_text)
- SUCCESS: Cross-chain link identified with high confidence (score > 0.8)
- PARTIAL: Multiple candidates found, report top-5 ranked by score
- FAILED: Tool limitations prevent further progress

## Report Format (IMPORTANT)
When reporting results with candidates, use this format:

```
[STATUS]: Brief summary of findings

Top Candidates (ranked by score):
1. [TXID] | [AMOUNT] DOGE | score=[SCORE] | [REASON]
2. [TXID] | [AMOUNT] DOGE | score=[SCORE] | [REASON]
...

Best match: [TXID] with score [SCORE]
Reasoning: [Why this is the best match]
```

Example:
```
PARTIAL: Found 5 candidate DOGE transactions in the time window.

Top Candidates:
1. 71b1ed12... | 614.31 DOGE | score=0.95 | fee_ratio=2.1%, timing=-15min
2. db0e7032... | 605.58 DOGE | score=0.72 | fee_ratio=3.8%, timing=-22min
3. 0357e74d... | 725.17 DOGE | score=0.45 | fee_ratio=15%, timing=-8min

Best match: 71b1ed1276b53803... (score=0.95, fee=2.1%)
```

## CRITICAL: How to Search for Source DOGE Transaction
After collecting BTC tx data and price data, you can calculate the expected DOGE amount.

### Option 1: If you have a DOGE address (from user hint)
- Calculate time window: BTC_timestamp - 1800 (30 min before) to BTC_timestamp
- Issue task: "Fetch DOGE address <addr> txs from <min_ts> to <max_ts>"
- Analyze returned txs for amount match

### Option 2: If you have a DOGE tx hash
- Issue task: "Fetch DOGE transaction <hash>"
- Verify the amount and timing match

### Option 3: If you have NEITHER address nor tx hash (PREFERRED for cross-chain discovery)
- Calculate time window: BTC_timestamp - 1800 to BTC_timestamp
- Calculate expected DOGE amount from price: BTC_amount / DOGE_BTC_price
- Issue task: "Search DOGE txs from <min_ts> to <max_ts> with amount <expected-10%> to <expected+10%>"
- This will scan DOGE blocks and return transactions matching the time and amount criteria
- Analyze the results to find the best match

### Analyzing Candidates (after search returns results)
After receiving candidate txs from search, if candidates > 1, do fine-grained analysis:

1. DO NOT search again - you already have the candidates from the search
2. For EACH candidate tx, fetch price at THAT candidate's timestamp (not the BTC tx timestamp):
   - Issue: "Fetch DOGE/BTC price at timestamp <candidate_block_time>"
3. After getting price for each candidate, calculate:
   - source_value_btc = candidate_doge_amount * price_at_candidate_time
   - Check bridge logic: source_value_btc >= dest_btc_amount (bridges never lose money)
   - If source_value_btc < dest_btc_amount: this candidate is INVALID, score = 0.1
   - If source_value_btc >= dest_btc_amount: VALID, score based on fee ratio
   - fee_ratio = (source_value_btc - dest_btc_amount) / source_value_btc
   - Good fee_ratio: 0.1% - 5%
4. After scoring ALL candidates, STOP and report TOP-5 ranked by score

CRITICAL: The search for txs happens ONCE. After that, only fetch prices for each candidate.
Do NOT repeat the search. Do NOT loop back to search again.

DO NOT issue vague tasks without parameters:
- "Fetch DOGE address transactions" ← WRONG (no address specified)
- "Find DOGE transaction" ← WRONG (use search_doge_txs_by_time instead)

## Handling Tool Limitations
If Fetcher reports gaps like "cannot search transactions by criteria" or "need specific tx hash":
- This is a VALID stopping condition
- Report to user what was found and what cannot be determined
- Do NOT ask Fetcher to retry with made-up data"""


class TraceOrchestratorAgent:
    """Trace Orchestrator Agent that controls the tracing workflow."""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=config.LLM_MODEL,
            temperature=config.LLM_TEMPERATURE,
            max_tokens=config.LLM_MAX_TOKENS
        ).with_structured_output(TraceOrchestratorOutput)

    def process(
        self,
        state: GraphState,
        fetch_report: Optional[dict] = None
    ) -> TraceOrchestratorOutput:
        """
        Process current state and optionally a fetch report.

        Args:
            state: Current graph state
            fetch_report: Optional report from Trace Fetcher

        Returns:
            Decision to continue with task brief or stop with answer
        """
        messages = self._build_messages(state, fetch_report)
        result = self.llm.invoke(messages)
        return result

    def _build_messages(
        self,
        state: GraphState,
        fetch_report: Optional[dict] = None
    ) -> List:
        """Build message list for LLM."""
        messages = [SystemMessage(content=TRACE_ORCHESTRATOR_SYSTEM_PROMPT)]

        # Add conversation history
        conv_messages = state.get("messages", [])
        for msg in conv_messages:
            messages.append(msg)

        # Add current state context
        blockchain_state = state.get("blockchain", {})
        trace_state = state.get("trace", {})

        context_parts = []

        # Transfers info
        transfers = blockchain_state.get("transfers", {})
        if transfers:
            context_parts.append("Current transfers in state:")
            for chain, chain_transfers in transfers.items():
                for tid, transfer in chain_transfers.items():
                    context_parts.append(f"  - {chain}: {tid}")

        # Cross-chain links
        cclinks = blockchain_state.get("cclinks", [])
        if cclinks:
            context_parts.append("Current cross-chain links:")
            for link in cclinks:
                context_parts.append(f"  - {link.id} (confidence: {link.confidence:.2f})")

        # Plan progress
        plan = trace_state.get("plan", {})
        if plan:
            context_parts.append(f"Plan iteration: {plan.get('iter', 0)}, cursor: {plan.get('cursor', 0)}")

        # Accumulated findings
        findings = trace_state.get("findings", [])
        if findings:
            context_parts.append(f"Accumulated findings ({len(findings)} total):")
            for f in findings:
                kind = f.get("kind", "?")
                fid = f.get("id", "?")
                data = f.get("data", {})
                if kind == "price":
                    price = data.get("price", "?")
                    context_parts.append(f"  - [price] {fid}: {price}")
                elif kind == "tx":
                    chain = data.get("chain", "?")
                    context_parts.append(f"  - [tx] {chain}: {fid}")
                    if data.get("outputs"):
                        context_parts.append(f"    Outputs: {data.get('outputs')[:3]}")
                    if data.get("block_time"):
                        context_parts.append(f"    Time: {data.get('block_time')}")
                elif kind == "address":
                    chain = data.get("chain", "?")
                    balance = data.get(f"balance_{chain.lower()}", "?")
                    context_parts.append(f"  - [address] {chain}: {fid}, balance: {balance}")
                elif kind == "search_txs":
                    # Show search results with candidates
                    context_parts.append(f"  - [search_txs] {fid}")
                    txs = data.get("transactions", [])
                    context_parts.append(f"    Candidates ({len(txs)} txs) - DO NOT SEARCH AGAIN:")
                    for tx in txs[:10]:
                        txid = tx.get("txid", "?")
                        total = tx.get("total_output_doge", 0)
                        btime = tx.get("block_time", "?")
                        context_parts.append(f"      - {txid} | {total:.2f} DOGE | time={btime}")
                elif kind == "address_txs":
                    context_parts.append(f"  - [address_txs] {fid}")
                    txs = data.get("transactions", [])
                    context_parts.append(f"    Transactions ({len(txs)} txs):")
                    for tx in txs[:10]:
                        txid = tx.get("txid", "?")[:16] + "..."
                        sent = tx.get("sent_doge") or tx.get("sent_btc") or 0
                        received = tx.get("received_doge") or tx.get("received_btc") or 0
                        btime = tx.get("block_time", "?")
                        context_parts.append(f"      - {txid} | sent={sent:.2f} recv={received:.2f} | time={btime}")

        # Errors
        errors = trace_state.get("errors", [])
        if errors:
            context_parts.append(f"Errors encountered: {len(errors)}")
            for err in errors[-3:]:  # Show last 3 errors
                context_parts.append(f"  - {err.get('where', 'unknown')}: {err.get('msg', '')}")

        if context_parts:
            context = "\n".join(context_parts)
            messages.append(HumanMessage(content=f"[Current State]\n{context}"))

        # Add fetch report if provided
        if fetch_report:
            report_str = self._format_fetch_report(fetch_report)
            messages.append(HumanMessage(content=f"[Fetch Report]\n{report_str}"))

        # Add instruction
        messages.append(HumanMessage(content="Based on the above, decide your next action. Return continue with a task_brief, or stop with an answer."))

        return messages

    def _format_fetch_report(self, report: dict) -> str:
        """Format fetch report for LLM consumption."""
        parts = [f"Task: {report.get('task', 'unknown')}"]

        findings = report.get("findings", [])
        if findings:
            parts.append("Findings:")
            for f in findings:
                parts.append(f"  - [{f.get('kind', 'unknown')}] {f.get('id', '')}: {f.get('rationale', '')}")
                # Include key data from findings
                data = f.get("data", {})
                if data:
                    # Extract important fields for the orchestrator
                    if data.get("chain"):
                        parts.append(f"    Chain: {data.get('chain')}")
                    if data.get("txid"):
                        parts.append(f"    TxID: {data.get('txid')}")
                    if data.get("block_time") or data.get("confirmed_time"):
                        parts.append(f"    Time: {data.get('block_time') or data.get('confirmed_time')}")
                    if data.get("inputs"):
                        parts.append(f"    Inputs: {data.get('inputs')[:3]}")  # First 3 inputs
                    if data.get("outputs"):
                        parts.append(f"    Outputs: {data.get('outputs')[:3]}")  # First 3 outputs
                    if data.get("total_btc"):
                        parts.append(f"    Total BTC: {data.get('total_btc')}")
                    if data.get("total_doge"):
                        parts.append(f"    Total DOGE: {data.get('total_doge')}")
                    if data.get("fee_btc"):
                        parts.append(f"    Fee BTC: {data.get('fee_btc')}")
                    if data.get("fee_doge"):
                        parts.append(f"    Fee DOGE: {data.get('fee_doge')}")
                    # Handle address_txs and search_txs findings - show transaction list for analysis
                    if data.get("transactions"):
                        txs = data.get("transactions", [])
                        parts.append(f"    Transaction List ({len(txs)} txs):")
                        for tx in txs[:10]:  # Show up to 10 txs
                            txid = tx.get("txid", "?")[:16] + "..."
                            btime = tx.get("block_time", "?")
                            # Handle both address_txs format (sent/received/net) and search_txs format (total_output)
                            if tx.get("total_output_doge") is not None:
                                # search_txs format
                                total = tx.get("total_output_doge", 0)
                                parts.append(f"      - {txid} | total_output={total:.2f} DOGE | time={btime}")
                            else:
                                # address_txs format
                                sent = tx.get("sent_doge") or tx.get("sent_btc") or 0
                                received = tx.get("received_doge") or tx.get("received_btc") or 0
                                net = tx.get("net_doge") or tx.get("net_btc") or 0
                                parts.append(f"      - {txid} | sent={sent:.2f} recv={received:.2f} net={net:.2f} | time={btime}")
                    if data.get("price"):
                        parts.append(f"    Price: {data.get('price')}")

        gaps = report.get("gaps", [])
        if gaps:
            parts.append("Gaps/Issues:")
            for g in gaps:
                parts.append(f"  - {g}")

        return "\n".join(parts)


def evaluate_crosschain_link(
    src_transfer: Transfer,
    dst_transfer: Transfer,
    src_op_id: str,
    dst_op_id: str,
    time_diff_seconds: int,
    value_diff_percent: float
) -> float:
    """
    Calculate confidence score for a potential cross-chain link.

    Uses the v0 minimal feature set:
    - F_time: Time proximity
    - F_value: Value consistency
    - F_unique: Uniqueness (simplified for v0)

    Args:
        src_transfer: Source chain transfer
        dst_transfer: Destination chain transfer
        src_op_id: Operation ID in source transfer
        dst_op_id: Operation ID in destination transfer
        time_diff_seconds: Absolute time difference
        value_diff_percent: Value difference as percentage (0-100)

    Returns:
        Confidence score (0-1)
    """
    import math

    # F_time: exp(-dt / tau)
    tau_time = config.CCLINK_TAU_TIME_BRIDGE  # Use bridge default
    f_time = math.exp(-abs(time_diff_seconds) / tau_time)

    # F_value: exp(-rel / tau)
    f_value = math.exp(-abs(value_diff_percent) / 100 / config.CCLINK_TAU_VALUE)

    # Weighted sum (simplified v0)
    score = (
        config.CCLINK_WEIGHT_TIME * f_time +
        config.CCLINK_WEIGHT_VALUE * f_value
    )

    # Normalize to 0-1
    max_score = config.CCLINK_WEIGHT_TIME + config.CCLINK_WEIGHT_VALUE
    confidence = min(score / max_score, 1.0)

    return confidence


def create_crosschain_link(
    src_chain: str,
    src_transfer_id: str,
    src_op_id: str,
    dst_chain: str,
    dst_transfer_id: str,
    dst_op_id: str,
    confidence: float
) -> CrossChainLink:
    """Create a CrossChainLink with proper ID."""
    src = OpRef(chain=src_chain, transfer_id=src_transfer_id, op_id=src_op_id)
    dst = OpRef(chain=dst_chain, transfer_id=dst_transfer_id, op_id=dst_op_id)

    return CrossChainLink(
        id=CrossChainLink.make_id(src, dst),
        src=src,
        dst=dst,
        confidence=confidence
    )
