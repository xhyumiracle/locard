"""
Alchemy API tools for Ethereum blockchain queries.

Provides access to Alchemy's enhanced APIs including asset transfers search.
API Documentation: https://docs.alchemy.com/reference/
"""

import logging
from typing import List, Dict, Any

import httpx
from langchain_core.tools import tool

import config
from src.clients.base import with_retry, cached, TransientError, FatalError, LoggingHTTPClient
from src.tools.models import EthTransfer

logger = logging.getLogger(__name__)


class AlchemyClient:
    """Alchemy API client for Ethereum queries."""

    def __init__(self, api_key: str = None, timeout: int = 60):
        """
        Initialize Alchemy client.

        Args:
            api_key: Alchemy API key (default: from config.ALCHEMY_API_KEY)
            timeout: Request timeout in seconds (default: 60)
        """
        self.api_key = api_key or config.ALCHEMY_API_KEY
        if not self.api_key:
            raise ValueError("Alchemy API key required. Set ALCHEMY_API_KEY in .env")

        self.base_url = f"https://eth-mainnet.g.alchemy.com/v2/{self.api_key}"

        raw_client = httpx.Client(
            timeout=timeout,
            headers={"Content-Type": "application/json"},
            follow_redirects=True
        )
        self.client = LoggingHTTPClient(raw_client, "alchemy")

    @cached("alchemy")
    @with_retry()
    def _request(self, method: str, params: List[Any]) -> Dict:
        """
        Make JSON-RPC request to Alchemy API.

        Args:
            method: JSON-RPC method name
            params: Method parameters

        Returns:
            Response result

        Raises:
            TransientError: For retryable errors (5xx, timeouts)
            FatalError: For non-retryable errors (4xx, invalid params)
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }

        response = self.client.post(self.base_url, json=payload)

        # Handle HTTP errors
        if response.status_code >= 500:
            raise TransientError(f"Alchemy server error: {response.status_code}")
        if response.status_code == 429:
            raise TransientError("Alchemy rate limit exceeded")
        if response.status_code >= 400:
            raise FatalError(f"Alchemy client error: {response.status_code} - {response.text[:200]}")

        response.raise_for_status()
        data = response.json()

        # Handle JSON-RPC errors
        if "error" in data:
            error = data["error"]
            error_msg = error.get("message", "Unknown error")
            raise FatalError(f"Alchemy API error: {error_msg}")

        return data.get("result", {})

    def get_block_by_timestamp(self, timestamp: int, closest: str = "after") -> int:
        """
        Get block number closest to a timestamp using binary search.

        Args:
            timestamp: Unix timestamp
            closest: "before" or "after"

        Returns:
            Block number closest to the timestamp
        """
        # Get latest block as upper bound
        latest_block_hex = self._request("eth_blockNumber", [])
        latest_block = int(latest_block_hex, 16)

        # Get latest block timestamp
        block_data = self._request("eth_getBlockByNumber", [latest_block_hex, False])
        latest_timestamp = int(block_data["timestamp"], 16)

        # If target timestamp is in the future, return latest
        if timestamp >= latest_timestamp:
            return latest_block

        # Estimate starting point using average block time
        avg_block_time = 12
        time_diff = latest_timestamp - timestamp
        estimated_diff = time_diff // avg_block_time
        estimated_block = max(0, latest_block - estimated_diff)

        # Binary search
        left = max(0, estimated_block - 1000)  # Search window: ±1000 blocks
        right = min(latest_block, estimated_block + 1000)

        logger.debug(f"Binary searching for timestamp {timestamp} in blocks {left}-{right}")

        # Find the block closest to target timestamp
        result_block = estimated_block
        min_diff = abs(latest_timestamp - timestamp)

        while left <= right:
            mid = (left + right) // 2

            # Get block timestamp
            mid_hex = hex(mid)
            block_data = self._request("eth_getBlockByNumber", [mid_hex, False])
            mid_timestamp = int(block_data["timestamp"], 16)

            diff = abs(mid_timestamp - timestamp)
            if diff < min_diff:
                min_diff = diff
                result_block = mid

            # Binary search
            if mid_timestamp < timestamp:
                left = mid + 1
            elif mid_timestamp > timestamp:
                right = mid - 1
            else:
                # Exact match
                result_block = mid
                break

        # Adjust based on closest parameter
        if closest == "before":
            # Make sure result block timestamp <= target timestamp
            block_hex = hex(result_block)
            block_data = self._request("eth_getBlockByNumber", [block_hex, False])
            block_ts = int(block_data["timestamp"], 16)
            while block_ts > timestamp and result_block > 0:
                result_block -= 1
                block_hex = hex(result_block)
                block_data = self._request("eth_getBlockByNumber", [block_hex, False])
                block_ts = int(block_data["timestamp"], 16)
        else:  # after
            # Make sure result block timestamp >= target timestamp
            block_hex = hex(result_block)
            block_data = self._request("eth_getBlockByNumber", [block_hex, False])
            block_ts = int(block_data["timestamp"], 16)
            while block_ts < timestamp and result_block < latest_block:
                result_block += 1
                block_hex = hex(result_block)
                block_data = self._request("eth_getBlockByNumber", [block_hex, False])
                block_ts = int(block_data["timestamp"], 16)

        logger.info(f"Found block {result_block} for timestamp {timestamp} (closest={closest})")
        return result_block

    def get_asset_transfers(
        self,
        from_block: int,
        to_block: int,
        category: List[str] = None,
        from_address: str = None,
        to_address: str = None,
        max_count: int = 1000
    ) -> List[Dict]:
        """
        Get asset transfers using alchemy_getAssetTransfers.

        Args:
            from_block: Starting block number
            to_block: Ending block number
            category: Transfer categories (default: ["external", "internal"])
            from_address: Filter by sender address
            to_address: Filter by recipient address
            max_count: Maximum results to return (default: 1000)

        Returns:
            List of transfer records
        """
        if category is None:
            category = ["external", "internal"]

        params = [{
            "fromBlock": hex(from_block),
            "toBlock": hex(to_block),
            "category": category,
            "withMetadata": True,
            "maxCount": hex(max_count)
        }]

        if from_address:
            params[0]["fromAddress"] = from_address
        if to_address:
            params[0]["toAddress"] = to_address

        result = self._request("alchemy_getAssetTransfers", params)
        return result.get("transfers", [])

    def close(self):
        """Close HTTP client."""
        self.client.close()


@tool
def search_eth_transfers_alchemy(
    min_timestamp: int = 0,
    max_timestamp: int = 0,
    min_amount: float = 0,
    max_amount: float = 0,
    from_address: str = "",
    to_address: str = "",
    direction: str = "both",
    limit: int = 100
) -> List[dict]:
    """
    Search ETH transfers by time and amount using Alchemy API.

    This tool searches ALL ETH transfers (both external transactions and internal calls)
    without requiring address filters. Uses Alchemy's getAssetTransfers API
    for efficient queries.

    IMPORTANT:
    - This is HIGHLY RECOMMENDED for ETH cross-chain tracing
    - Works without address filters (unlike blockchair calls endpoint)
    - Searches both external transactions AND internal transfers
    - Amount values use ETH unit (not wei)
    - Free tier: 3M compute units/month (sufficient for most use cases)

    Args:
        min_timestamp: Start time (Unix), 0 = no lower bound
        max_timestamp: End time (Unix), 0 = no upper bound
        min_amount: Min transfer amount in ETH (e.g., 22.5), 0 = no filter
        max_amount: Max transfer amount in ETH (e.g., 28.2), 0 = no upper bound
        from_address: Optional sender address filter
        to_address: Optional recipient address filter
        direction: Transfer direction - "in" (recipient), "out" (sender), "both"
        limit: Max results (default 100)

    Returns:
        List[EthTransfer]: List of ETH transfers matching criteria.
        Each transfer contains: txid, from_addr, to_addr, amount (ETH), block_time

    Example:
        # Search for 22-28 ETH transfers in a 30-minute window
        search_eth_transfers_alchemy(
            min_timestamp=1766255375,
            max_timestamp=1766257175,
            min_amount=22.88,
            max_amount=25.34,
            direction="both",
            limit=100
        )
    """
    if min_timestamp <= 0 and max_timestamp <= 0:
        raise ValueError("At least one of min_timestamp or max_timestamp must be specified")

    client = AlchemyClient()

    try:
        # Convert timestamps to block numbers using binary search
        # No buffer needed as binary search is accurate
        if min_timestamp > 0:
            from_block = client.get_block_by_timestamp(min_timestamp, "before")
        else:
            from_block = 0

        if max_timestamp > 0:
            to_block = client.get_block_by_timestamp(max_timestamp, "after")
        else:
            # Get latest block
            latest_hex = client._request("eth_blockNumber", [])
            to_block = int(latest_hex, 16)

        logger.info(f"Searching ETH transfers: blocks {from_block}-{to_block}, "
                    f"{min_amount}-{max_amount} ETH, direction={direction}")

        # Determine category based on direction
        if direction == "in" and to_address:
            # If searching for incoming and have recipient, use both categories
            category = ["external", "internal"]
            filter_from = None
            filter_to = to_address
        elif direction == "out" and from_address:
            # If searching for outgoing and have sender, use both categories
            category = ["external", "internal"]
            filter_from = from_address
            filter_to = None
        else:
            # No address filter or "both" direction - search everything
            category = ["external", "internal"]
            filter_from = from_address if from_address else None
            filter_to = to_address if to_address else None

        # Get transfers from Alchemy
        # Use a larger maxCount to avoid missing results
        raw_transfers = client.get_asset_transfers(
            from_block=from_block,
            to_block=to_block,
            category=category,
            from_address=filter_from,
            to_address=filter_to,
            max_count=min(limit * 10, 1000)  # Request more than needed for filtering
        )

        logger.info(f"Alchemy returned {len(raw_transfers)} raw transfers")

        # Filter by amount and direction
        results = []
        for transfer in raw_transfers:
            # Skip if not ETH
            if transfer.get("asset") != "ETH":
                continue

            # Get amount
            value = float(transfer.get("value", 0))

            # Check amount range
            if min_amount > 0 and value < min_amount:
                continue
            if max_amount > 0 and value > max_amount:
                continue

            # Check direction if no address filter was provided
            if not from_address and not to_address:
                # We need both from and to for direction filtering
                from_addr = transfer.get("from", "")
                to_addr = transfer.get("to", "")

                # For direction filtering without address, we can't determine
                # So we include all transfers and let the caller filter
                pass

            # Get block timestamp
            block_num = transfer.get("blockNum", "0x0")
            if isinstance(block_num, str):
                block_num = int(block_num, 16)

            # Convert to EthTransfer model
            eth_transfer = EthTransfer(
                chain="ETH",
                txid=transfer.get("hash"),
                status="confirmed",
                sender=transfer.get("from"),
                recipient=transfer.get("to"),
                amount=value,
                block_time=0,  # Will be filled by block lookup if needed
                block_height=block_num,
                # fee is None by default (Alchemy getAssetTransfers doesn't provide fee)
                meta={"category": transfer.get("category", "external")}
            )
            results.append(eth_transfer.model_dump())

            if len(results) >= limit:
                break

        logger.info(f"Found {len(results)} ETH transfers matching criteria")
        return results

    finally:
        client.close()
