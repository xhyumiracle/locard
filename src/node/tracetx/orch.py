import logging
import config
from src.agents.trace_orchestrator import TraceOrchestratorAgent
from src.state.tracetx_state import TraceTxState
from src.models.core import dst_info_schema_to_state, src_info_schema_to_state

logger = logging.getLogger(__name__)


def orchestrator_node(state: TraceTxState) -> dict:
    updates = {}
    
    orchestrator = TraceOrchestratorAgent()

    
    # ===============================================
    # fail if max iterations reached
    # ===============================================
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

    # ===============================================
    # Before agent move: merge (pending trajectory + inbox finding refs) to trajectories
    # ===============================================
    inbox_findings = state.get("inbox_findings", [])
    pending_trajectory = state.get("pending_trajectory", {})

    if pending_trajectory:
        last_trajectory = dict(pending_trajectory)
        last_trajectory["findings_ref"] = [finding["id"] for finding in inbox_findings]
        updates.update({
            "trajectories": [last_trajectory],
        })

    # ===============================================
    # Agent move
    # ===============================================
    result = orchestrator.process(state)

    # ===============================================
    # After agent move: update state
    # ===============================================
    action = result.action
    logger.info(f"TraceTx Orchestrator action: {action}")

    # Common updates for all actions
    updates.update({
        "iteration": iteration + 1,
        "action": action,
        "findings": inbox_findings,
        "inbox_findings": [],
        "inbox_gaps": [],
        "pending_trajectory": {
            "action": action,
            "task_brief": result.task_brief,
            "findings_ref": []
        }
    })

    # Action-specific updates
    if action == "fetch":
        pass # task brief no need, use pending_trajectory.
    elif action == "done":
        # Ready for scoring - extract finding IDs
        updates["candidates_finding_ids"] = result.candidates_finding_ids
    elif action == "fail":
        # Failed - stop without scoring
        updates["fail_reason"] = result.fail_reason
        updates["result"] = {"success": False, "data": None, "reason": result.fail_reason}
    else:
        raise Exception(f"Unknown action: {action}")

    # ===============================================
    # append new trajectory
    # ===============================================
    updates["pending_trajectory"] = {
        "action": action,
        "task_brief": result.task_brief,
        "findings_ref": []
    }

    # Include dst_info/src_info if provided (needed by derive_node)
    # Convert from Schema (Pydantic) to State model (dataclass)
    if result.dst_info:
        updates["dst_info"] = dst_info_schema_to_state(result.dst_info)
    if result.src_info:
        updates["src_info"] = src_info_schema_to_state(result.src_info)
    return updates


# def candidates_to_cclinks(candidates: List[CandidateOutput], dst_info, src_info):

#     # Build CrossChainLink list with unified validation
#     links: list[CrossChainLink] = []

#     dst_transfer = dst_info_to_transfer(dst_info)

#     if not dst_transfer:
#         raise Exception(f"Destination transfer {dst_info} not found in state")

#     # Validate dst op_id exists
#     dst_op_id = dst_info['op_id']
#     if dst_op_id not in dst_transfer.operations:
#         available_ops = list(dst_transfer.operations.keys())
#         raise Exception(
#             f"dst_info.op_id {dst_op_id} not found in dst_transfer "
#             f"(available: {available_ops})"
#         )

#     for c in candidates:
#         candidate_transfer = candidate_to_transfer(c, src_info)

#         link = CrossChainLink(
#             id=CrossChainLink.make_id(
#                 src_transfer=candidate_transfer,
#                 src_op_id=c.op_id,
#                 dst_transfer=dst_transfer,
#                 dst_op_id=dst_op_id
#             ),
#             src_transfer=candidate_transfer,
#             src_op_id=c.op_id,
#             dst_transfer=dst_transfer,
#             dst_op_id=dst_op_id,
#             price_min=c.price_min,
#             price_max=c.price_max,
#         )
#         links.append(link)
#     return links

# # convert candidate to transfer
# def candidate_to_transfer(candidate: CandidateOutput, src_info) -> Transfer:
#     """Convert candidate to Transfer. src_info is dict from state."""
#     return Transfer(
#         txid=candidate.txid,
#         chain=src_info['chain'],
#         type="utxo" if config.is_utxo_chain(src_info['chain']) else "account",
#         block_time=candidate.block_time,
#         status="confirmed",
#         block_height=None,
#         block_hash=None,
#         operations={candidate.op_id: Operation(
#             op_id=candidate.op_id,
#             account=None,
#             amount=candidate.amount,
#             asset=src_info['asset'],
#             decimals=config.get_asset_decimals(src_info['chain'], src_info['asset']),
#             spent_coin_id=None
#         )}
#     )

# def dst_info_to_transfer(dst_info) -> Transfer:
#     """Convert dst_info to Transfer. dst_info is dict from state."""
#     return Transfer(
#         txid=dst_info['txid'],
#         chain=dst_info['chain'],
#         type="utxo" if config.is_utxo_chain(dst_info['chain']) else "account",
#         block_time=dst_info['time'],
#         status="confirmed",
#         block_height=None,
#         block_hash=None,
#         operations={dst_info['op_id']: Operation(
#             op_id=dst_info['op_id'],
#             account=None,
#             amount=dst_info['amount'],
#             asset=dst_info['asset'],
#             decimals=config.get_asset_decimals(dst_info['chain'], dst_info['asset']),
#             spent_coin_id=None
#         )}
#     )