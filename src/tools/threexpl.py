"""
3xpl ClickHouse API tools for blockchain analytics.

Provides access to 3xpl's OLAP database for efficient cross-chain queries.
API: http://olap.3xpl.net:71/
"""

import json
import logging
from typing import List, Dict, Any

import httpx
from langchain_core.tools import tool

from src.clients.base import with_retry, cached, TransientError, FatalError, LoggingHTTPClient
from src.tools.models import Eth3xplTransfer

logger = logging.getLogger(__name__)


class ClickHouse3xplClient:
    """3xpl ClickHouse API client for blockchain analytics."""

    BASE_URL = "http://olap.3xpl.net:71/"
    SOURCE_NAME = "3xpl-clickhouse"

    def __init__(self, username: str = "mvp", password: str = "mvp", timeout: int = 60):
        """
        Initialize 3xpl ClickHouse client.

        Args:
            username: ClickHouse username (default: mvp for test access)
            password: ClickHouse password (default: mvp for test access)
            timeout: Query timeout in seconds (default: 60, OLAP queries can be slow)
        """
        self.username = username
        self.password = password

        # CRITICAL: Disable proxy to avoid 502 errors
        # 3xpl ClickHouse doesn't work through proxies
        raw_client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; BlockchainClient/1.0)"},
            follow_redirects=True,
            trust_env=False  # Ignore system proxy settings
        )
        self.client = LoggingHTTPClient(raw_client, self.SOURCE_NAME)

    @cached("3xpl")
    @with_retry()
    def query(self, sql: str, format: str = "JSONEachRow") -> str:
        """
        Execute SQL query and return raw response text.

        Args:
            sql: SQL query string
            format: ClickHouse output format (default: JSONEachRow)

        Returns:
            Raw response text (multiple JSON lines for JSONEachRow)
        """
        # Add FORMAT clause if not present
        if "FORMAT" not in sql.upper():
            sql = f"{sql}\nFORMAT {format}"

        response = self.client.post(
            self.BASE_URL,
            data=sql,
            auth=(self.username, self.password)
        )

        # Handle response status
        if response.status_code >= 500:
            raise TransientError(f"ClickHouse server error: {response.status_code}")
        if response.status_code == 400:
            error_msg = response.text[:200] if response.text else "Unknown error"
            raise FatalError(f"Invalid SQL query: {error_msg}")

        response.raise_for_status()
        return response.text

    def close(self):
        self.client.close()


@tool
def search_eth_transfers_3xpl(
    min_timestamp: int = 0,
    max_timestamp: int = 0,
    min_amount: float = 0,
    max_amount: float = 0,
    direction: str = "in",
    limit: int = 100
) -> List[dict]:
    """
    Search ETH transfers by time and amount using 3xpl ClickHouse. No address required.

    This tool searches ALL ETH transfers (including internal calls/traces) without
    requiring recipient or sender address filters. Uses 3xpl's analytics database
    for efficient OLAP queries.

    IMPORTANT:
    - This is the RECOMMENDED tool for ETH cross-chain tracing
    - Works without address filters (unlike blockchair calls endpoint)
    - Searches both top-level transactions AND internal transfers
    - Amount values use ETH unit (not wei)

    Args:
        min_timestamp: Start time (Unix), 0 = no lower bound
        max_timestamp: End time (Unix), 0 = no upper bound
        min_amount: Min transfer amount in ETH (e.g., 25.5), 0 = no filter
        max_amount: Max transfer amount in ETH (e.g., 28.2), 0 = no upper bound
        direction: Transfer direction - "in" (recipient), "out" (sender), "both"
        limit: Max results (default 100, can be higher for OLAP queries)

    Returns:
        List[Eth3xplTransfer]: List of ETH transfers matching criteria.
        Each transfer contains: txid, recipient, amount (ETH), block_time

    Example:
        # Search for 25-28 ETH transfers in a 30-minute window
        search_eth_transfers_3xpl(
            min_timestamp=1747858711,
            max_timestamp=1747860511,
            min_amount=25.47,
            max_amount=28.22,
            direction="in",
            limit=100
        )
    """
    if min_timestamp <= 0 and max_timestamp <= 0:
        raise ValueError("At least one of min_timestamp or max_timestamp must be specified")

    # Convert direction to sign filter
    # sign = 1: incoming (recipient), sign = -1: outgoing (sender)
    if direction == "in":
        sign_filter = "AND sign = 1"
    elif direction == "out":
        sign_filter = "AND sign = -1"
    elif direction == "both":
        sign_filter = ""
    else:
        raise ValueError(f"Invalid direction: {direction}. Use 'in', 'out', or 'both'")

    # Build time filter
    time_conditions = []
    if min_timestamp > 0:
        time_conditions.append(f"time >= toDateTime({min_timestamp})")
    if max_timestamp > 0:
        time_conditions.append(f"time <= toDateTime({max_timestamp})")
    time_filter = " AND ".join(time_conditions) if time_conditions else "1=1"

    # Build amount filter (convert ETH to wei for database query)
    amount_conditions = []
    if min_amount > 0:
        min_wei = int(min_amount * 1e18)
        amount_conditions.append(f"effect >= {min_wei}")
    if max_amount > 0:
        max_wei = int(max_amount * 1e18)
        amount_conditions.append(f"effect <= {max_wei}")
    amount_filter = " AND ".join(amount_conditions) if amount_conditions else "1=1"

    # Build SQL query
    # Note: We select recipient-side events (sign=1) for cross-chain matching
    # The 'address' field is the recipient when sign=1
    query = f"""
    SELECT
        transaction AS txid,
        toUnixTimestamp(time) AS block_time,
        address AS recipient,
        effect / 1e18 AS amount,
        block,
        module
    FROM events
    WHERE blockchain = 'ethereum'
      AND module = 'ethereum-main'
      AND {time_filter}
      AND {amount_filter}
      {sign_filter}
    ORDER BY time DESC
    LIMIT {limit}
    FORMAT JSONEachRow
    """

    logger.info(f"Querying 3xpl for ETH transfers: {min_timestamp}-{max_timestamp}, "
                f"{min_amount}-{max_amount} ETH, direction={direction}, limit={limit}")

    client = ClickHouse3xplClient()

    try:
        response_text = client.query(query)

        # Parse JSON lines
        results = []
        if response_text.strip():
            for line in response_text.strip().split('\n'):
                event_data = json.loads(line)

                # Convert to Eth3xplTransfer model
                transfer = Eth3xplTransfer(
                    chain="ETH",
                    txid=event_data["txid"],
                    recipient=event_data["recipient"],
                    amount=float(event_data["amount"]),
                    block_time=int(event_data["block_time"]),
                    module=event_data.get("module", "ethereum-main"),
                    block=event_data.get("block")
                )
                results.append(transfer.model_dump())

        logger.info(f"Found {len(results)} ETH transfers from 3xpl")
        return results

    finally:
        client.close()
