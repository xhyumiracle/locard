"""
Pure Python candidate scoring logic.

Implements the scoring rules based on fee rate range:
- Price range: [price_min, price_max] from Binance (raw, no buffer)
- Price direction: SOURCE_in_DESTINATION, i.e., 1 src_coin = X dst_coin
- expected_dst = src_amount * price (multiplication, no division)
- Buffers applied: lower_bound = price_min * src_amount
                   upper_bound = price_max * (1 + PRICE_MAX_DEVIATION_RATE) * src_amount
- Fee rate range: [fee_rate_min, fee_rate_max] computed from actual dst_amount vs price range
- Exclusion: fee_rate_min > PRICE_MAX_FEE_RATE (dst too small) or fee_rate_max < 0 (dst too large)
- Feature score f_amount: based on fee rate range width (wider = more possible, better)

Works with CrossChainLink objects that have:
- src_transfer, dst_transfer: Transfer references (self-contained)
- price_min, price_max: raw price range at src tx time (1 src_coin = X dst_coin)
"""

import math
from typing import List, Optional, Literal
from dataclasses import dataclass

import logging
import config
from src.models.core import CrossChainLink, Transfer
from src.state.tracetx_state import TraceTxState
from mashumaro import DataClassDictMixin

logger = logging.getLogger(__name__)


@dataclass
class ScoringParams(DataClassDictMixin):
    """
    Config-only parameters for scoring.

    Instance-specific data (amounts, timestamps, prices) are in CrossChainLink and Transfer.
    Defaults are in config.py (SCORING_* and PRICE_MAX_* constants).
    """
    tau_time: int           # time decay constant for f_time
    w_time: float           # weight for time feature (f_time)
    w_amount: float          # weight for amount feature (f_amount, based on fee rate range)
    max_fee_rate: float     # max acceptable fee rate (exclusion threshold)
    max_deviation_rate: float  # max price deviation across platforms (upper buffer)


@dataclass
class ScoreTable(DataClassDictMixin):
    """
    Complete scoring output with recursive serialization support.

    Use .to_dict() to serialize entire structure (including nested CrossChainLinks).
    Use .from_dict() to deserialize from JSON dict.
    """
    status: Literal["SUCCESS", "PARTIAL", "FAILED", "NO_CANDIDATES"]
    params: ScoringParams
    candidates: List[CrossChainLink]   # sorted by confidence descending, excluded ones at end
    best_match: Optional[str]          # link id of best match (None if no valid candidates)
    summary: str                       # brief summary (e.g., "Found 3 valid candidates, 1 excluded")



def score_node(state: TraceTxState) -> dict:
    """Scoring. Logic node not LLM"""
    cclinks = state["cclinks"]

    logger.info(f"Scoring {len(cclinks)} candidates")

    score_table = score_candidates(links=cclinks)

    logger.info(f"Score table: {format_score_table(score_table)}")

    return {
        "score_table": score_table,  # Add to state top-level for easy access
        "result": {
            "success": True,
            "data": score_table  # Keep for compatibility
        }
     }


def score_single_link(
    link: CrossChainLink,
    params: ScoringParams
) -> CrossChainLink:
    """
    Score a single CrossChainLink and fill in computed fields.

    Fee rate range calculation:
    - low_amt = price_min * src_amount (min expected dst amount at raw price)
    - high_amt = price_max * src_amount (max expected dst amount at raw price)
    - With buffers:
      - fee_rate_min = max(0, (low_amt - dst_amt) / low_amt)
      - fee_rate_max = (high_amt * (1 + DEVIATION) - dst_amt) / (high_amt * (1 + DEVIATION))

    Exclusion rules:
    - fee_rate_min > PRICE_MAX_FEE_RATE: dst amount too small (fee too high)
    - fee_rate_max < 0: dst amount too large (impossible, exceeds max price)
    - time_diff < 0: source tx after destination tx

    Args:
        link: CrossChainLink to score (will be mutated). Must have src_transfer and dst_transfer set.
        params: Scoring parameters

    Returns:
        The same CrossChainLink with scoring fields filled in
    """
    src_transfer = link.src_transfer
    dst_transfer = link.dst_transfer

    # Get timestamps
    src_time = src_transfer.block_time or 0
    dst_time = dst_transfer.block_time or 0

    # Compute time_diff
    link.time_diff = dst_time - src_time

    # Get source amount from operation by op_id
    src_op = src_transfer.operations.get(link.src_op_id)
    if not src_op or src_op.amount is None:
        link.excluded = True
        link.exclude_reason = f"Could not find source op {link.src_op_id} or amount {src_op.amount} is None in transfer"
        link.confidence = 0.0
        return link
    src_amount = src_op.amount

    # Get destination amount from operation by op_id
    dst_op = dst_transfer.operations.get(link.dst_op_id)
    if not dst_op or dst_op.amount is None:
        link.excluded = True
        link.exclude_reason = f"Could not find dst op {link.dst_op_id} or amount {dst_op.amount} is None in transfer"
        link.confidence = 0.0
        return link
    dst_amount = dst_op.amount

    # Check price data - must exist (bug if missing)
    if link.price_min is None or link.price_max is None:
        raise ValueError(
            f"CrossChainLink {link.id} missing price data: "
            f"price_min={link.price_min}, price_max={link.price_max}"
        )

    # Get scoring params
    max_fee_rate = params.max_fee_rate
    max_deviation_rate = params.max_deviation_rate

    # Compute fee rate range
    # low_amt: min expected dst amount (using price_min, no buffer)
    # high_amt_buffered: max expected dst amount (using price_max * (1 + deviation))
    low_amt = link.price_min * src_amount
    high_amt_buffered = link.price_max * (1 + max_deviation_rate) * src_amount

    # fee_rate_min: min possible fee rate (lower bound, determined by low_amt)
    # When dst_amt >= low_amt, fee_rate_min = 0 (or negative, clamped to 0)
    link.fee_rate_min = max(0, (low_amt - dst_amount) / low_amt) if low_amt > 0 else 0

    # fee_rate_max: max possible fee rate (upper bound, determined by high_amt_buffered)
    link.fee_rate_max = (high_amt_buffered - dst_amount) / high_amt_buffered

    # Check hard conditions
    if link.time_diff < 0:
        link.excluded = True
        link.exclude_reason = f"negative time_diff ({link.time_diff}s) - source after destination"
    elif link.fee_rate_min > max_fee_rate:
        # dst amount too small - even at lowest price, fee would exceed max acceptable
        link.excluded = True
        link.exclude_reason = f"fee_rate_min ({link.fee_rate_min:.2%}) > max acceptable ({max_fee_rate:.0%})"
    elif link.fee_rate_max < 0:
        # src amount too small - even at highest price with deviation buffer, cannot produce this dst amount
        link.excluded = True
        link.exclude_reason = f"fee_rate_max ({link.fee_rate_max:.2%}) < 0 - src amount too small for this dst"

    # Compute feature scores
    tau_time = params.tau_time

    # f_time: time proximity score
    if link.time_diff >= 0:
        link.f_time = round(math.exp(-link.time_diff / tau_time), 4)
    else:
        link.f_time = 0.0

    # f_amount: based on fee rate range width relative to theoretical max range
    # Wider range = more possible fee rates = higher probability of being correct
    #
    # Theoretical max fee_rate range:
    # - When dst_amt = low_amt: fee_rate_min = 0, fee_rate_max = (high_buffered - low) / high_buffered
    # - So max_range = (high_amt_buffered - low_amt) / high_amt_buffered
    #
    # Normalize: actual_range / max_range, clamped to [0, 1]
    if link.fee_rate_min is not None and link.fee_rate_max is not None and high_amt_buffered > 0:
        range_width = link.fee_rate_max - link.fee_rate_min
        max_range = (high_amt_buffered - low_amt) / high_amt_buffered
        link.f_amount = round(min(1.0, max(0, range_width / max_range)), 4) if max_range > 0 else 0.0
    else:
        link.f_amount = 0.0

    # Compute final score (confidence)
    w_time = params.w_time
    w_amount = params.w_amount

    if link.excluded:
        link.confidence = 0.0
    else:
        link.confidence = round(
            (w_time * link.f_time + w_amount * link.f_amount) / (w_time + w_amount),
            4
        )

    return link


def determine_status(valid_links: List[CrossChainLink]) -> str:
    """
    Determine scoring status based on valid candidates.

    Rules:
    - SUCCESS: Top candidate has clear lead (score_2 < score_1 * 0.8)
    - PARTIAL: Multiple close candidates (≥2 within 20%)
    - NO_CANDIDATES: No valid candidates
    """
    if not valid_links:
        return "NO_CANDIDATES"

    if len(valid_links) == 1:
        return "SUCCESS"

    top_score = valid_links[0].confidence
    second_score = valid_links[1].confidence

    # Check if second is within 20% of top
    if second_score >= top_score * 0.8:
        return "PARTIAL"
    else:
        return "SUCCESS"


def score_candidates(
    links: List[CrossChainLink],
    tau_time: int = config.SCORING_TAU_TIME,
    w_time: float = config.SCORING_W_TIME,
    w_amount: float = config.SCORING_W_VALUE,
    max_fee_rate: float = config.PRICE_MAX_FEE_RATE,
    max_deviation_rate: float = config.PRICE_MAX_DEVIATION_RATE,
) -> ScoreTable:
    """
    Score all candidate links and produce a ScoreTable.

    Args:
        links: List of CrossChainLink candidates (each must have src_transfer, dst_transfer,
               and price_min/price_max set)
        tau_time: Time decay constant for f_time
        w_time: Weight for time feature
        w_amount: Weight for amount feature (based on fee rate range width)
        max_fee_rate: Max acceptable fee rate (exclusion threshold)
        max_deviation_rate: Max price deviation across platforms (upper buffer)

    Returns:
        ScoreTable with all scored links and summary
    """
    params = ScoringParams(
        tau_time=tau_time,
        w_time=w_time,
        w_amount=w_amount,
        max_fee_rate=max_fee_rate,
        max_deviation_rate=max_deviation_rate,
    )

    if not links:
        return ScoreTable(
            status="NO_CANDIDATES",
            params=params,
            candidates=[],
            best_match=None,
            summary="No candidates provided for scoring"
        )

    # Score all links
    scored: List[CrossChainLink] = []
    for link in links:
        score_single_link(link, params)
        scored.append(link)

    # Separate valid and excluded
    valid = [l for l in scored if not l.excluded]
    excluded = [l for l in scored if l.excluded]

    # Sort valid by confidence descending
    valid.sort(key=lambda x: x.confidence, reverse=True)

    # Determine status
    status = determine_status(valid)

    # Best match
    best_match = valid[0].id if valid else None

    # Summary
    total = len(links)
    valid_count = len(valid)
    excluded_count = len(excluded)

    if valid_count == 0:
        summary = f"All {total} candidates excluded (failed hard conditions)"
    elif excluded_count == 0:
        summary = f"Found {valid_count} valid candidates"
    else:
        summary = f"Found {valid_count} valid candidates, {excluded_count} excluded"

    # Combine: valid first (sorted by confidence), then excluded
    all_links = valid + excluded

    return ScoreTable(
        status=status,
        params=params,
        candidates=all_links,
        best_match=best_match,
        summary=summary
    )



def format_score_table(table: ScoreTable) -> str:
    """Format scoring table for LLM consumption.

    Filters out large Transfer objects, only keeping essential fields.
    """
    lines = [
        f"Status: {table.status}",
        f"Summary: {table.summary}",
        "",
        "Scoring Parameters:",
        f"  - tau_time: {table.params.tau_time}s",
        f"  - max_fee_rate: {table.params.max_fee_rate:.2%}",
        f"  - max_deviation_rate: {table.params.max_deviation_rate:.2%}",
        f"  - w_time: {table.params.w_time}",
        f"  - w_amount: {table.params.w_amount}",
        "",
    ]

    if table.best_match:
        lines.append(f"Best Match: {table.best_match}")
        lines.append("")

    lines.append("Candidates (sorted by confidence):")
    for i, link in enumerate(table.candidates, 1):
        # Determine if we should show op_id based on transfer type
        show_src_op = link.src_transfer.type == "utxo"
        show_dst_op = link.dst_transfer.type == "utxo"

        if link.excluded:
            lines.append(f"  {i}. [EXCLUDED] {link.src_chain}:{link.src_transfer.txid}")
            lines.append(f"     Reason: {link.exclude_reason}")
        else:
            # Get operations directly via op_id
            src_op = link.src_transfer.operations[link.src_op_id]
            dst_op = link.dst_transfer.operations[link.dst_op_id]

            # Get amounts
            src_amount = src_op.amount if src_op.amount is not None else "N/A"
            dst_amount = dst_op.amount if dst_op.amount is not None else "N/A"

            # Get timestamps
            src_timestamp = link.src_transfer.block_time if link.src_transfer.block_time else "N/A"
            dst_timestamp = link.dst_transfer.block_time if link.dst_transfer.block_time else "N/A"

            # Format source line with amount and timestamp
            src_op_str = f" (op: {src_op.op_id})" if show_src_op else ""
            lines.append(f"  {i}. {link.src_chain}:{link.src_transfer.txid}{src_op_str}")
            lines.append(f"     Source: {src_amount} {link.src_chain}, timestamp: {src_timestamp}")

            # Format destination line with amount and timestamp
            dst_op_str = f" (op: {dst_op.op_id})" if show_dst_op else ""
            lines.append(f"     → {link.dst_chain}:{link.dst_transfer.txid}{dst_op_str}")
            lines.append(f"     Destination: {dst_amount} {link.dst_chain}, timestamp: {dst_timestamp}")

            # Time difference and fee rate
            time_diff_str = f"{link.time_diff}s" if link.time_diff is not None else "N/A"
            fee_rate_str = f"[{link.fee_rate_min:.2%}, {link.fee_rate_max:.2%}]" if link.fee_rate_min is not None else "N/A"
            lines.append(f"     Time diff: {time_diff_str}, Fee rate range: {fee_rate_str}")
            lines.append(f"     Confidence: F_time={link.f_time:.4f}, F_amount={link.f_amount:.4f}, Final={link.confidence:.4f}")

    return "\n".join(lines)
