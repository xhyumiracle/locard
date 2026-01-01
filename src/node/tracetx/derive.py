import logging
from src.state.tracetx_state import TraceTxState
from src.tools.models import PriceRange

logger = logging.getLogger(__name__)

def derive_node(state: TraceTxState) -> dict:
    """Derive the search window from the dest transfer."""
    updates = {}

    prev_derived = state.get("derived") or {}
    updates = {
        "search_window": dict(prev_derived.get("search_window") or {})
    }

    logger.info(f"Derive node: Enter")

    # Step 1: Time window - now calculated by orchestrator itself (block_time - search_time_span)
    dest_info = state.get("dest_info") or {}
    dest_time = dest_info.get("time")
    if dest_time:
        search_time_span = state["params"]["search_time_span"]
        dst_time = ensure_ts_seconds(dest_time)
        start_ts = dst_time - search_time_span
        end_ts = dst_time
        updates["search_window"]["time"] = {"start_ts": start_ts, "end_ts": end_ts}
    else:
        logger.info(f"Derive node: skip derive time window, dest_time={dest_time}")

    # Step 2: Derive search amount window from price findings
    src_asset = state.get("src_info", {}).get("asset")
    dest_asset = dest_info.get("asset")
    dest_amount = dest_info.get("amount")
    # # use updates rather than prev_derived, because we want to use the current time window
    # search_time_window = updates.get("search_window",{}).get("time")
    
    # if src_asset and dest_asset and dest_amount and dest_time and search_time_window: # only on search_window is set
    #     start_ts, end_ts = search_time_window.get("start_ts"), search_time_window.get("end_ts")
    dest_time = dest_info.get("time")

    if src_asset and dest_asset and dest_amount and dest_time:
        # Calculate time window same as orch does (block_time - search_time_span, block_time)
        search_time_span = state["params"]["search_time_span"]
        end_ts = ensure_ts_seconds(dest_time)
        start_ts = end_ts - search_time_span

        fid_dest_in_src = f"{dest_asset}_in_{src_asset}@time({start_ts}-{end_ts})"
        fid_src_in_dest = f"{src_asset}_in_{dest_asset}@time({start_ts}-{end_ts})"
        # Look for matching price finding (search both findings and inbox_findings)
        price_range = None
        all_findings = (state.get("findings") or []) + (state.get("inbox_findings") or [])
        for finding in all_findings:
            if finding.get("kind") != "price":
                continue
            fid = finding.get("id", "")
            # Match: DEST_in_SRC (direct) or SRC_in_DEST (need to invert)
            if fid == fid_dest_in_src:
                price_range = PriceRange(**finding.get("data"))
                break
            elif fid == fid_src_in_dest:
                data = finding.get("data")
                # Invert: if 1 SRC = X DEST, then 1 DEST = 1/X SRC
                price_range = PriceRange(
                    price_min=1.0 / data["price_max"],
                    price_max=1.0 / data["price_min"],
                    via=data.get("via")
                )
                break

        if price_range:
            updates["search_window"]["amount"] = {
                "min": dest_amount * price_range.price_min,
                "max": dest_amount * price_range.price_max
            }
        else:
            logger.info(f"no matching price finding with {fid_dest_in_src} or {fid_src_in_dest}")
            logger.info(f"- inbox_findings={state.get('inbox_findings')}")
            logger.info(f"- findings={state.get('findings')}")

            # Clear amount window if no matching price (e.g., time span changed)
            updates["search_window"].pop("amount", None)
    else:
        logger.info(f"Derive node: skip derive amount window, src_asset={src_asset}, dest_asset={dest_asset}, dest_amount={dest_amount}, dest_time={dest_time}")
 
    logger.info(f"Derive node: Leaving with search_window={updates.get('search_window')}")
    return {"derived": updates}

def ensure_ts_seconds(ts: int) -> int:
    """Ensure timestamp is in seconds."""
    if ts > 1_000_000_000_000: # is ms
        return ts // 1000
    else:
        return ts # is sec