"""
Validate and prepare candidate data for scoring.

Responsibilities:
- Extract finding data by IDs from orchestrator
- Validate data completeness and format
- Build CrossChainLink objects for scoring
- Raise errors if data is invalid or missing
"""
import logging
from typing import List
from src.state.tracetx_state import TraceTxState, get_all_findings
from src.models.core import CrossChainLink, Operation, Transfer, DstInfo, SrcInfo
from src.models.finding import Finding, find_by_id, find_matching_price
import src.tools.converters as converter
import config

logger = logging.getLogger(__name__)



def validate_node(state: TraceTxState) -> dict:
    """
    Validate and prepare candidates for scoring.

    Extracts search_txs and price data based on finding IDs from orchestrator,
    validates data, and builds CrossChainLink objects.

    Raises:
        ValueError: If finding IDs are missing, findings not found, or data is invalid

    Returns:
        dict with cclinks ready for scoring
    """
    # Get finding IDs that contains all candidates from state (set by orchestrator)
    candidates_finding_ids = state.get("candidates_finding_ids")
    if not candidates_finding_ids:
        raise ValueError(f"Missing candidates_finding_ids in state")

    logger.info(f"Validating findings: candidates={candidates_finding_ids}")

    # Get findings from state and find specific ones by ID
    all_findings = get_all_findings(state)
    candidates_findings = []
    for fid in candidates_finding_ids:
        finding = find_by_id(findings=all_findings, id=fid, ignore_case_sensitive=True)
        if not finding:
            raise ValueError(f"Finding not found: {fid}")
        candidates_findings.append(finding)

    # Merge and flatten data 
    candidate_txs = [tx for candidate_finding in candidates_findings for tx in candidate_finding.get("data", [])]

    logger.info(f"Found {len(candidate_txs)} candidate transactions")

    # Build CrossChainLinks
    cclinks = candidates_to_cclinks(candidate_txs, state.get("dst_info"), all_findings, state["params"]["check_time_span"])

    if not cclinks:
        raise ValueError(
            f"Failed to create any CrossChainLinks from {len(candidate_txs)} transactions"
        )

    logger.info(f"Created {len(cclinks)} CrossChainLinks for scoring")

    return {
        "cclinks": cclinks
    }


def candidates_to_cclinks(candidate_txs: List[dict], dst_info: DstInfo, all_findings: List[Finding], check_time_span: int) -> List[CrossChainLink]:
    """Build CrossChainLinks from candidate transactions."""
    links: list[CrossChainLink] = []

    dst_transfer = dst_info_to_transfer(dst_info)

    if not dst_transfer:
        raise Exception(f"Destination transfer {dst_info} not found in state")

    dst_op = dst_transfer.operations[dst_info.op_id]

    for candidate in candidate_txs:
        candidate_transfer = converter.dict_to_transfer(candidate)

        # Candidate must have exactly one vout operation (recipient/output)
        # Multiple operations are OK (e.g., EthTransfer/EthCall have both vin+vout),
        # but we need exactly one vout to match as the source output
        vout_ops = {k: v for k, v in candidate_transfer.operations.items() if k.startswith("vout:")}
        if len(vout_ops) != 1:
            raise ValueError(
                f"Candidate transfer {candidate_transfer.txid} must have exactly 1 vout operation, "
                f"found {len(vout_ops)}: {list(vout_ops.keys())}"
            )
        src_op = list(vout_ops.values())[0]

        # Find matching price range for the candidate check time window
        start_ts, end_ts = config.get_tracetx_check_time_window(candidate_transfer.block_time, check_time_span)
        price_range = find_matching_price(
            findings=all_findings,
            coin=src_op.asset,
            quote=dst_op.asset,
            start_ts=start_ts,
            end_ts=end_ts
        )

        if not price_range:
            raise ValueError(f"No price range found for candidate {candidate_transfer.txid}")

        link = CrossChainLink(
            id=CrossChainLink.make_id(
                src_transfer=candidate_transfer,
                src_op_id=src_op.op_id,
                dst_transfer=dst_transfer,
                dst_op_id=dst_op.op_id
            ),
            src_transfer=candidate_transfer,
            src_op_id=src_op.op_id,
            dst_transfer=dst_transfer,
            dst_op_id=dst_op.op_id,
            price_min=price_range.price_min,
            price_max=price_range.price_max,
        )
        links.append(link)
    return links


def dst_info_to_transfer(dst_info) -> Transfer:
    """Convert dst_info to Transfer. dst_info is DstInfo dataclass from state."""
    return Transfer(
        txid=dst_info.txid,
        chain=dst_info.chain,
        type="utxo" if config.is_utxo_chain(dst_info.chain) else "account",
        block_time=dst_info.time,
        status="confirmed",
        block_height=None,
        block_hash=None,
        operations={dst_info.op_id: Operation(
            op_id=dst_info.op_id,
            account=None,
            amount=dst_info.amount,
            asset=dst_info.asset,
            decimals=config.get_asset_decimals(dst_info.chain, dst_info.asset),
            spent_coin_id=None
        )}
    )