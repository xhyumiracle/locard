import logging
from typing import List
import config
from src.agents.trace_orchestrator import CandidateOutput, TraceOrchestratorAgent
from src.models import Operation
from src.state.tracetx_state import DestInfo, SrcInfo, TraceTxState
from src.models.core import CrossChainLink, Transfer

logger = logging.getLogger(__name__)


def orchestrator_node(state: TraceTxState) -> dict:
    orchestrator = TraceOrchestratorAgent()

    iteration = state.get("iteration", 0)
    if iteration >= config.TRACE_MAX_ITERATIONS:
        logger.warning("Max trace iterations reached")
        return {
            "action": "stop", 
            "result": {
                "success": False,
                "reason": "Maximum iterations reached. Unable to complete trace."
            }
        }

    # agent move
    result = orchestrator.process(state)

    # post-process
    action = result.action
    logger.info(f"TraceTx Orchestrator action: {action}")

    updates = {}
    if action == "fetch":
        updates = {
            "iteration": iteration + 1,
            "action": "fetch",
            "task_brief": result.task_brief,
            "findings": state.get("inbox_findings", []),
            "inbox_findings": [] # clear inbox
        }
    elif action == "score":
        # Convert Pydantic models to dicts
        candidates = result.candidates
        # dest_info and src_info can be Pydantic objects or dicts from state
        dest_info = result.dest_info.model_dump() if result.dest_info else state["dest_info"]
        src_info = result.src_info.model_dump() if result.src_info else state["src_info"]
        cclinks = candidates_to_cclinks(candidates, dest_info, src_info)
        updates = {
            # dont add iter since it is finishing
            "action": "score",
            "cclinks": cclinks,
            "findings": state.get("inbox_findings", []), # no need, keep records for future reference
            "inbox_findings": []
        }
    elif action == "stop":
        # Stop without scoring (e.g., no candidates found)
        updates = {
            "action": "stop",
            "stop_reason": result.stop_reason,
            "result": {"success": False, "data": None, "reason": result.stop_reason}
        }
    else:
        raise Exception(f"Unknown action: {action}")

    # Include dest_info if provided (needed by derive_node)
    if result.dest_info:
        updates["dest_info"] = result.dest_info.model_dump()
    if result.src_info:
        updates["src_info"] = result.src_info.model_dump()
    return updates


def candidates_to_cclinks(candidates: List[CandidateOutput], dest_info, src_info):

    # Build CrossChainLink list with unified validation
    links: list[CrossChainLink] = []

    dst_transfer = dest_info_to_transfer(dest_info)

    if not dst_transfer:
        raise Exception(f"Destination transfer {dest_info} not found in state")

    # Validate dest op_id exists
    dest_op_id = dest_info['op_id']
    if dest_op_id not in dst_transfer.operations:
        available_ops = list(dst_transfer.operations.keys())
        raise Exception(
            f"dest_info.op_id {dest_op_id} not found in dst_transfer "
            f"(available: {available_ops})"
        )

    for c in candidates:
        candidate_transfer = candidate_to_transfer(c, src_info)

        link = CrossChainLink(
            id=CrossChainLink.make_id(
                src_transfer=candidate_transfer,
                src_op_id=c.op_id,
                dst_transfer=dst_transfer,
                dst_op_id=dest_op_id
            ),
            src_transfer=candidate_transfer,
            src_op_id=c.op_id,
            dst_transfer=dst_transfer,
            dst_op_id=dest_op_id,
            price_min=c.price_min,
            price_max=c.price_max,
        )
        links.append(link)
    return links

# convert candidate to transfer
def candidate_to_transfer(candidate: CandidateOutput, src_info) -> Transfer:
    """Convert candidate to Transfer. src_info is dict from state."""
    return Transfer(
        txid=candidate.txid,
        chain=src_info['chain'],
        type="utxo" if config.is_utxo_chain(src_info['chain']) else "account",
        block_time=candidate.block_time,
        status="confirmed",
        block_height=None,
        block_hash=None,
        operations={candidate.op_id: Operation(
            op_id=candidate.op_id,
            account=None,
            amount=candidate.amount,
            asset=src_info['asset'],
            decimals=config.get_asset_decimals(src_info['chain'], src_info['asset']),
            spent_coin_id=None
        )}
    )

def dest_info_to_transfer(dest_info) -> Transfer:
    """Convert dest_info to Transfer. dest_info is dict from state."""
    return Transfer(
        txid=dest_info['txid'],
        chain=dest_info['chain'],
        type="utxo" if config.is_utxo_chain(dest_info['chain']) else "account",
        block_time=dest_info['time'],
        status="confirmed",
        block_height=None,
        block_hash=None,
        operations={dest_info['op_id']: Operation(
            op_id=dest_info['op_id'],
            account=None,
            amount=dest_info['amount'],
            asset=dest_info['asset'],
            decimals=config.get_asset_decimals(dest_info['chain'], dest_info['asset']),
            spent_coin_id=None
        )}
    )