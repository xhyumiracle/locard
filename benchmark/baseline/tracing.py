from __future__ import annotations

import re
from typing import Any

import config
from src.models.core import CrossChainLink, DstInfo, SrcInfo
from src.node.tracetx.validate import dst_info_to_transfer
from src.tools.binance import get_price_binance
from src.tools.blockchair import get_txs_blockchair, search_eth_calls_blockchair, search_utxo_outputs_blockchair
from src.tools.bitquery import search_eth_transfers_bitquery
from src.tools.calculators import calculate_search_amount_window, calculate_search_time_window
from src.tools.converters import dict_to_transfer
from src.tools.electrs import get_txs_doge_electrs
from src.tools.threexpl import search_eth_transfers_3xpl

from benchmark.baseline.observation import TraceQueryContext


QUERY_RE = re.compile(
    r"What is the source transaction for this cross-chain\s+"
    r"(?P<dst_asset>[A-Z0-9]+)\s+output to\s+(?P<dst_address>\S+)\s+"
    r"in tx\s+(?P<dst_txid>[A-Fa-f0-9]+)\s+on\s+(?P<dst_chain>[A-Z0-9\-]+),\s+"
    r"given that it originates from\s+(?P<src_asset>[A-Z0-9]+)\s+on\s+"
    r"(?P<src_chain>[A-Z0-9\-]+)\?",
    re.MULTILINE,
)


def parse_query(query: str) -> dict[str, str]:
    compact = " ".join(query.split())
    match = QUERY_RE.fullmatch(compact)
    if not match:
        raise ValueError(f"Unsupported query format: {query}")
    return match.groupdict()


def choose_granularity(start_ts: int, end_ts: int) -> str:
    duration = max(1, end_ts - start_ts)
    if duration <= 3600:
        return "1s"
    if duration <= 60_000:
        return "1m"
    if duration <= 300_000:
        return "5m"
    return "15m"


def invoke_tool(tool, args: dict[str, Any]) -> Any:
    return tool.invoke(args)


def choose_destination_fetch_tool(chain: str):
    chain = chain.upper()
    if chain == "DOGE":
        return get_txs_doge_electrs
    return get_txs_blockchair


def choose_source_search_tool(chain: str):
    chain = chain.upper()
    if config.is_utxo_chain(chain):
        return [search_utxo_outputs_blockchair]
    if chain == "ETH":
        return [search_eth_transfers_bitquery]
    raise ValueError(f"Unsupported source chain for candidate search: {chain}")


def normalize_txid(txid: str) -> str:
    return txid.lower().removeprefix("0x")


def try_match_operation(transfer, address: str):
    matches = [
        op for op in transfer.operations.values()
        if op.op_id.startswith("vout:") and op.account and (op.account.address or "").upper() == address.upper()
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"Multiple destination outputs matched address {address} in tx {transfer.txid}")
    return None


def fetch_eth_destination_call(txid: str, dst_address: str, block_time: int) -> dict[str, Any]:
    calls = invoke_tool(
        search_eth_calls_blockchair,
        {
            "min_timestamp": block_time - 120,
            "max_timestamp": block_time + 120,
            "recipient": dst_address,
            "limit": 100,
        },
    )
    matched = [call for call in calls if normalize_txid(call.get("txid", "")) == normalize_txid(txid)]
    if not matched:
        raise ValueError(f"Could not find destination output for address {dst_address} in tx {txid}")
    if len(matched) > 1:
        raise ValueError(f"Multiple ETH internal calls matched address {dst_address} in tx {txid}")
    return matched[0]


def fetch_price_range(
    coin: str,
    quote: str,
    start_ts: int,
    end_ts: int,
    lower_buffer_perc: float,
    upper_buffer_perc: float,
) -> dict[str, Any]:
    granularity = choose_granularity(start_ts, end_ts)
    args = {
        "coin": coin,
        "quote": quote,
        "granularity": granularity,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "lower_buffer_perc": lower_buffer_perc,
        "upper_buffer_perc": upper_buffer_perc,
    }
    try:
        return invoke_tool(get_price_binance, args)
    except Exception:
        if granularity != "1s":
            raise
        args["granularity"] = "1m"
        return invoke_tool(get_price_binance, args)


def fetch_destination_tx(chain: str, txid: str) -> dict[str, Any]:
    chain = chain.upper()
    tool = choose_destination_fetch_tool(chain)
    if tool is get_txs_doge_electrs:
        txs = invoke_tool(tool, {"tx_hashes": txid})
    else:
        txs = invoke_tool(tool, {"chain": chain, "tx_hashes": txid})
    if not txs:
        raise ValueError(f"Destination tx not found for {chain}:{txid}")
    return txs[0]


def extract_query_context(parsed_query: dict[str, str], dst_tx: dict[str, Any]) -> TraceQueryContext:
    dst_transfer = dict_to_transfer(dst_tx)
    dst_address = parsed_query["dst_address"]
    matched_op = try_match_operation(dst_transfer, dst_address)
    if matched_op is None and parsed_query["dst_chain"].upper() == "ETH":
        dst_call = fetch_eth_destination_call(
            txid=parsed_query["dst_txid"],
            dst_address=dst_address,
            block_time=int(dst_transfer.block_time),
        )
        dst_transfer = dict_to_transfer(dst_call)
        matched_op = try_match_operation(dst_transfer, dst_address)
    if matched_op is None:
        raise ValueError(f"Could not find destination output for address {dst_address} in tx {parsed_query['dst_txid']}")
    return TraceQueryContext(
        src_info=SrcInfo(chain=parsed_query["src_chain"].upper(), asset=parsed_query["src_asset"].upper()),
        dst_info=DstInfo(
            txid=normalize_txid(dst_transfer.txid or parsed_query["dst_txid"]),
            chain=parsed_query["dst_chain"].upper(),
            asset=parsed_query["dst_asset"].upper(),
            op_id=matched_op.op_id,
            amount=float(matched_op.amount),
            time=int(dst_transfer.block_time),
        ),
        dst_address=dst_address,
    )


def fetch_search_price_range(context: TraceQueryContext, search_start: int, search_end: int, search_price_buffer: float) -> dict[str, Any]:
    return fetch_price_range(
        coin=context.dst_info.asset,
        quote=context.src_info.asset,
        start_ts=search_start,
        end_ts=search_end,
        lower_buffer_perc=search_price_buffer,
        upper_buffer_perc=search_price_buffer,
    )


def fetch_source_candidates(
    context: TraceQueryContext,
    search_start: int,
    search_end: int,
    src_amount_min: float,
    src_amount_max: float,
    limit: int,
) -> tuple[list[dict[str, Any]], str]:
    errors: list[str] = []
    for tool in choose_source_search_tool(context.src_info.chain):
        if tool is search_utxo_outputs_blockchair:
            args = {
                "chain": context.src_info.chain,
                "min_timestamp": search_start,
                "max_timestamp": search_end,
                "min_amount": src_amount_min,
                "max_amount": src_amount_max,
                "limit": limit,
            }
        elif tool is search_eth_transfers_3xpl:
            args = {
                "min_timestamp": search_start,
                "max_timestamp": search_end,
                "min_amount": src_amount_min,
                "max_amount": src_amount_max,
                "direction": "in",
                "limit": limit,
            }
        else:
            args = {
                "min_timestamp": search_start,
                "max_timestamp": search_end,
                "min_amount": src_amount_min,
                "max_amount": src_amount_max,
                "limit": limit,
            }
        try:
            return invoke_tool(tool, args), tool.name
        except Exception as exc:
            errors.append(f"{tool.name}: {exc}")
    raise ValueError("All source candidate search tools failed: " + " | ".join(errors))


def fetch_candidate_price_range(candidate: dict[str, Any], context: TraceQueryContext, check_time_span: int) -> tuple[dict[str, Any], tuple[int, int]]:
    center = int(candidate["block_time"])
    start_ts = center - check_time_span
    end_ts = center + check_time_span
    price = fetch_price_range(
        coin=context.src_info.asset,
        quote=context.dst_info.asset,
        start_ts=start_ts,
        end_ts=end_ts,
        lower_buffer_perc=0.0,
        upper_buffer_perc=0.0,
    )
    return price, (start_ts, end_ts)


def build_cclinks(
    candidates: list[dict[str, Any]],
    context: TraceQueryContext,
    check_time_span: int,
) -> tuple[list[CrossChainLink], list[dict[str, Any]]]:
    dst_transfer = dst_info_to_transfer(context.dst_info)
    cclinks: list[CrossChainLink] = []
    step4_logs: list[dict[str, Any]] = []

    for candidate in candidates:
        src_transfer = dict_to_transfer(candidate)
        src_op_id = next(iter(src_transfer.operations.keys()))
        price_range, (start_ts, end_ts) = fetch_candidate_price_range(candidate, context, check_time_span)
        cclinks.append(
            CrossChainLink(
                id=CrossChainLink.make_id(
                    src_transfer=src_transfer,
                    src_op_id=src_op_id,
                    dst_transfer=dst_transfer,
                    dst_op_id=context.dst_info.op_id,
                ),
                src_transfer=src_transfer,
                src_op_id=src_op_id,
                dst_transfer=dst_transfer,
                dst_op_id=context.dst_info.op_id,
                price_min=float(price_range["price_min"]),
                price_max=float(price_range["price_max"]),
            )
        )
        step4_logs.append(
            {
                "candidate_txid": candidate["txid"],
                "candidate_time": int(candidate["block_time"]),
                "window": [start_ts, end_ts],
                "price_min": float(price_range["price_min"]),
                "price_max": float(price_range["price_max"]),
            }
        )
    return cclinks, step4_logs


def execute_trace_steps(query_id: str, query: str, params: dict[str, Any]) -> tuple[list[CrossChainLink], dict[str, Any], list[str]]:
    parsed = parse_query(query)
    dst_fetch_tool = choose_destination_fetch_tool(parsed["dst_chain"])
    dst_tx = fetch_destination_tx(parsed["dst_chain"], parsed["dst_txid"])
    context = extract_query_context(parsed, dst_tx)

    search_window = invoke_tool(
        calculate_search_time_window,
        {
            "dst_block_time": context.dst_info.time,
            "search_time_span": params["search_time_span"],
            "search_time_offset": params["search_time_offset"] or None,
        },
    )
    search_start = int(search_window["start"])
    search_end = int(search_window["end"])

    search_price = fetch_search_price_range(
        context=context,
        search_start=search_start,
        search_end=search_end,
        search_price_buffer=params["search_price_buffer"],
    )
    ratio_min = float(search_price["price_min"])
    ratio_max = float(search_price["price_max"])

    amount_window = invoke_tool(
        calculate_search_amount_window,
        {
            "dst_amount": context.dst_info.amount,
            "dst_asset": context.dst_info.asset,
            "src_asset": context.src_info.asset,
            "price_min": ratio_min,
            "price_max": ratio_max,
            "price_coin": context.dst_info.asset,
            "price_quote": context.src_info.asset,
        },
    )
    src_amount_min = float(amount_window["min"])
    src_amount_max = float(amount_window["max"])

    candidates, source_search_tool = fetch_source_candidates(
        context=context,
        search_start=search_start,
        search_end=search_end,
        src_amount_min=src_amount_min,
        src_amount_max=src_amount_max,
        limit=params["search_limit"],
    )
    cclinks, step4_logs = build_cclinks(
        candidates=candidates,
        context=context,
        check_time_span=params["check_time_span"],
    )

    baseline = {
        "workflow": "heuristic_trace_orchestrator",
        "step_1": {
            "dst_fetch_tool": dst_fetch_tool.name,
            "src_info": context.src_info.to_dict(),
            "dst_info": {**context.dst_info.to_dict(), "address": context.dst_address},
        },
        "step_2": {
            "search_window": [search_start, search_end],
            "price_tool": "get_price_binance",
            "ratio_src_per_dst_min": ratio_min,
            "ratio_src_per_dst_max": ratio_max,
        },
        "step_3": {
            "candidate_search_tool": source_search_tool,
            "src_amount_window": [src_amount_min, src_amount_max],
            "candidate_count": len(candidates),
            "used_fallback": False,
        },
        "step_4": step4_logs,
    }
    log_lines = [
        f"query_id={query_id}",
        f"query={query}",
        f"step_1 dst_fetch_tool={dst_fetch_tool.name} dst_txid={context.dst_info.txid} dst_amount={context.dst_info.amount} dst_time={context.dst_info.time}",
        f"step_2 search_window={search_start}-{search_end} ratio_src_per_dst=[{ratio_min}, {ratio_max}]",
        f"step_3 candidate_search_tool={source_search_tool} src_amount_window=[{src_amount_min}, {src_amount_max}] candidates={len(candidates)} fallback=False",
        *[
            "step_4 "
            f"candidate={item['candidate_txid']} "
            f"window={item['window'][0]}-{item['window'][1]} "
            f"price_dst_per_src=[{item['price_min']}, {item['price_max']}]"
            for item in step4_logs
        ],
    ]
    return cclinks, baseline, log_lines
