import config
from src.agents.trace_fetcher import TraceFetcherAgent
from src.state.tracetx_state import TraceTxState
import src.tools.converters as converter
from src.tools.models import AccountTx, UtxoTx
import logging

logger = logging.getLogger(__name__)

def fetcher_node(state: TraceTxState) -> dict:
    task_brief = state["task_brief"]

    logger.info(f"Trace Fetcher executing: {task_brief}...")

    fetcher = TraceFetcherAgent()
    result = fetcher.fetch(task_brief, state)
    findings = result["findings"]
    gaps = result["gaps"]

    logger.info(f"Fetcher found {len(findings)} findings, {len(gaps)} gaps")

    return {
        "inbox_findings": findings, 
        "inbox_gaps": gaps, 
    }

    # # Convert tx findings to Transfer and store in trace state # TODO: may not need?
    # transfers_update = {}
    # for finding in findings:
    #     if finding["kind"] != "tx":
    #         continue

    #     data = finding.get("data", {})

    #     # Handle list result (from get_txs tools) - should be single item for kind="tx"
    #     if isinstance(data, list):
    #         if len(data) != 1:
    #             logger.warning(f"kind='tx' finding has {len(data)} items, expected 1")
    #             continue
    #         data = data[0]

    #     try:
    #         chain = data["chain"]

    #         if config.is_utxo_chain(chain):
    #             utxo_tx = UtxoTx(**data)
    #             transfer = converter.utxo_tx_to_transfer(utxo_tx)
    #         else:
    #             account_tx = AccountTx(**data)
    #             transfer = converter.account_tx_to_transfer(account_tx)

    #         if chain not in transfers_update:
    #             transfers_update[chain] = {}
    #         transfers_update[chain][transfer.id] = transfer
    #     except Exception as e:
    #         logger.warning(f"Failed to convert tx finding to Transfer: {e}")
