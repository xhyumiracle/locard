import logging
# Imports below are unused while derive is disabled, but preserved for rollback
# import config
# from src.state.tracetx_state import TraceTxState, get_all_findings
# from src.tools.models import PriceRange
# from src.models.finding import build_finding_id, find_matching_price
from src.state.tracetx_state import TraceTxState

logger = logging.getLogger(__name__)

def derive_node(state: TraceTxState) -> dict:
    """Derive the search window from the dst transfer.

    NOTE: This node is currently DISABLED in favor of calculator tools for orchestrator.
    The code is preserved for reference and potential rollback if calculator tools prove unstable.

    To re-enable: uncomment the code blocks below and re-enable in the workflow graph.
    """
    logger.info(f"Derive node: Enter (DISABLED - using calculator tools instead)")

    # Return empty updates - orchestrator uses calculator tools directly
    return {"derived": {}}

    # ==================== DISABLED CODE BELOW ====================
    # This code is preserved for reference. To re-enable:
    # 1. Delete the early return above
    # 2. Uncomment all code below
    # 3. Re-enable derive node in the workflow graph
    # ==================== DISABLED CODE BELOW ====================

    # updates = {}
    #
    # prev_derived = state.get("derived") or {}
    # updates = {
    #     "search_window": dict(prev_derived.get("search_window") or {})
    # }
    #
    # logger.info(f"Derive node: Enter")
    #
    # # Step 1: Time window - now calculated by orchestrator itself (block_time - search_time_span)
    # dst_info = state.get("dst_info")
    # dst_time = dst_info.time if dst_info else None
    # if dst_time:
    #     search_time_span = state["params"]["search_time_span"]
    #     start_ts, end_ts = config.get_tracetx_search_time_window(dst_time, search_time_span)
    #     updates["search_window"]["time"] = {"start_ts": start_ts, "end_ts": end_ts}
    # else:
    #     logger.debug(f"Derive node: skip derive time window, dst_time={dst_time}")
    #
    # # Step 2: Derive search amount window from price findings
    # src_info = state.get("src_info")
    # src_asset = src_info.asset if src_info else None
    # dst_asset = dst_info.asset if dst_info else None
    # dst_amount = dst_info.amount if dst_info else None
    #
    # if src_asset and dst_asset and dst_amount and dst_time:
    #     # Calculate time window same as orch does (block_time - search_time_span, block_time)
    #     search_time_span = state["params"]["search_time_span"]
    #     start_ts, end_ts = config.get_tracetx_search_time_window(dst_time, search_time_span)
    #
    #     # Build finding IDs using centralized interface
    #     fid_dst_in_src = build_finding_id("price",
    #         coin=dst_asset,
    #         quote=src_asset,
    #         start_ts=start_ts,
    #         end_ts=end_ts
    #     )
    #     fid_src_in_dst = build_finding_id("price",
    #         coin=src_asset,
    #         quote=dst_asset,
    #         start_ts=start_ts,
    #         end_ts=end_ts
    #     )
    #
    #     # Look for matching price finding (search both findings and inbox_findings)
    #     price_range = None
    #
    #     all_findings = get_all_findings(state)
    #
    #     price_range = find_matching_price(
    #         findings=all_findings,
    #         coin=dst_asset,
    #         quote=src_asset,
    #         start_ts=start_ts,
    #         end_ts=end_ts
    #     )
    #
    #     if price_range:
    #         updates["search_window"]["amount"] = {
    #             "min": dst_amount * price_range.price_min,
    #             "max": dst_amount * price_range.price_max,
    #             "asset": src_asset  # Mark the asset unit for LLM clarity
    #         }
    #     else:
    #         logger.debug(f"no matching price finding with {fid_dst_in_src} or {fid_src_in_dst}")
    #         logger.debug(f"- inbox_findings={state.get('inbox_findings')}")
    #         logger.debug(f"- findings={state.get('findings')}")
    #
    #         # Clear amount window if no matching price (e.g., time span changed)
    #         updates["search_window"].pop("amount", None)
    # else:
    #     logger.debug(f"Derive node: skip derive amount window, src_asset={src_asset}, dst_asset={dst_asset}, dst_amount={dst_amount}, dst_time={dst_time}")
    #
    # logger.info(f"Derive node: Leaving with search_window={updates.get('search_window')}")
    # return {"derived": updates}
