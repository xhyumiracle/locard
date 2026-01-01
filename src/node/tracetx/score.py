"""
Pure Python candidate scoring logic.

Implements the scoring rules based on fee rate range:
- Price range: [price_min, price_max] from Binance (raw, no buffer)
- Price direction: SOURCE_in_DEST, i.e., 1 src_coin = X dst_coin
- expected_dst = src_amount * price (multiplication, no division)
- Buffers applied: lower_bound = price_min * src_amount
                   upper_bound = price_max * (1 + PRICE_MAX_DEVIATION_RATE) * src_amount
- Fee rate range: [fee_rate_min, fee_rate_max] computed from actual dest_amount vs price range
- Exclusion: fee_rate_min > PRICE_MAX_FEE_RATE (dest too small) or fee_rate_max < 0 (dest too large)
- Feature score f_amount: based on fee rate range width (wider = more possible, better)

Works with CrossChainLink objects that have:
- src_transfer, dst_transfer: Transfer references (self-contained)
- price_min, price_max: raw price range at src tx time (1 src_coin = X dst_coin)
"""

import math
from typing import List, Optional, Literal
from typing_extensions import TypedDict

import logging
import config
from src.models.core import CrossChainLink, Transfer
from src.state.tracetx_state import TraceTxState

logger = logging.getLogger(__name__)


class ScoringParams(TypedDict):
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


class ScoringTable(TypedDict):
    """Complete scoring output."""
    status: Literal["SUCCESS", "PARTIAL", "FAILED", "NO_CANDIDATES"]
    params: ScoringParams
    candidates: List[CrossChainLink]   # sorted by confidence descending, excluded ones at end
    best_match: Optional[str]          # link id of best match (None if no valid candidates)
    summary: str                       # brief summary (e.g., "Found 3 valid candidates, 1 excluded")



def score_node(state: TraceTxState) -> dict:
    """Scoring. Logic node not LLM"""
    cclinks = state["cclinks"]

    logger.info(f"Scoring {len(cclinks)} candidates")

    scoring_table = score_candidates(links=cclinks)

    logger.info(f"Scoring result: {scoring_table['status']}, best match: {scoring_table['best_match']}")

    return {
        "result": {
            "success": True,
            "data": scoring_table
        }
     } # write to subgraph state as subgraph output


def score_single_link(
    link: CrossChainLink,
    params: ScoringParams
) -> CrossChainLink:
    """
    Score a single CrossChainLink and fill in computed fields.

    Fee rate range calculation:
    - low_amt = price_min * src_amount (min expected dest amount at raw price)
    - high_amt = price_max * src_amount (max expected dest amount at raw price)
    - With buffers:
      - fee_rate_min = max(0, (low_amt - dest_amt) / low_amt)
      - fee_rate_max = (high_amt * (1 + DEVIATION) - dest_amt) / (high_amt * (1 + DEVIATION))

    Exclusion rules:
    - fee_rate_min > PRICE_MAX_FEE_RATE: dest amount too small (fee too high)
    - fee_rate_max < 0: dest amount too large (impossible, exceeds max price)
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
        link.exclude_reason = f"Could not find dest op {link.dst_op_id} or amount {dst_op.amount} is None in transfer"
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
    max_fee_rate = params.get("max_fee_rate", config.PRICE_MAX_FEE_RATE)
    max_deviation_rate = params.get("max_deviation_rate", config.PRICE_MAX_DEVIATION_RATE)

    # Compute fee rate range
    # low_amt: min expected dest amount (using price_min, no buffer)
    # high_amt_buffered: max expected dest amount (using price_max * (1 + deviation))
    low_amt = link.price_min * src_amount
    high_amt_buffered = link.price_max * (1 + max_deviation_rate) * src_amount

    # fee_rate_min: min possible fee rate (lower bound, determined by low_amt)
    # When dest_amt >= low_amt, fee_rate_min = 0 (or negative, clamped to 0)
    link.fee_rate_min = max(0, (low_amt - dst_amount) / low_amt) if low_amt > 0 else 0

    # fee_rate_max: max possible fee rate (upper bound, determined by high_amt_buffered)
    link.fee_rate_max = (high_amt_buffered - dst_amount) / high_amt_buffered

    # Check hard conditions
    if link.time_diff < 0:
        link.excluded = True
        link.exclude_reason = f"negative time_diff ({link.time_diff}s) - source after destination"
    elif link.fee_rate_min > max_fee_rate:
        # dest amount too small - even at lowest price, fee would exceed max acceptable
        link.excluded = True
        link.exclude_reason = f"fee_rate_min ({link.fee_rate_min:.2%}) > max acceptable ({max_fee_rate:.0%})"
    elif link.fee_rate_max < 0:
        # src amount too small - even at highest price with deviation buffer, cannot produce this dest amount
        link.excluded = True
        link.exclude_reason = f"fee_rate_max ({link.fee_rate_max:.2%}) < 0 - src amount too small for this dest"

    # Compute feature scores
    tau_time = params.get("tau_time", config.SCORING_TAU_TIME)

    # f_time: time proximity score
    if link.time_diff >= 0:
        link.f_time = round(math.exp(-link.time_diff / tau_time), 4)
    else:
        link.f_time = 0.0

    # f_amount: based on fee rate range width relative to theoretical max range
    # Wider range = more possible fee rates = higher probability of being correct
    #
    # Theoretical max fee_rate range:
    # - When dest_amt = low_amt: fee_rate_min = 0, fee_rate_max = (high_buffered - low) / high_buffered
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
    w_time = params.get("w_time", config.SCORING_W_TIME)
    w_amount = params.get("w_amount", config.SCORING_W_VALUE)

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
) -> ScoringTable:
    """
    Score all candidate links and produce a ScoringTable.

    Args:
        links: List of CrossChainLink candidates (each must have src_transfer, dst_transfer,
               and price_min/price_max set)
        tau_time: Time decay constant for f_time
        w_time: Weight for time feature
        w_amount: Weight for amount feature (based on fee rate range width)
        max_fee_rate: Max acceptable fee rate (exclusion threshold)
        max_deviation_rate: Max price deviation across platforms (upper buffer)

    Returns:
        ScoringTable with all scored links and summary
    """
    params = ScoringParams(
        tau_time=tau_time,
        w_time=w_time,
        w_amount=w_amount,
        max_fee_rate=max_fee_rate,
        max_deviation_rate=max_deviation_rate,
    )

    if not links:
        return ScoringTable(
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

    return ScoringTable(
        status=status,
        params=params,
        candidates=all_links,
        best_match=best_match,
        summary=summary
    )
