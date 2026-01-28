"""
Bitquery GraphQL API tools for multi-chain blockchain queries.

Provides access to Bitquery's GraphQL APIs for querying blockchain data.
API Documentation: https://docs.bitquery.io/
"""

import logging
from typing import List, Dict, Any
from datetime import datetime

import httpx
from langchain_core.tools import tool

import config
from src.clients.base import with_retry, cached, TransientError, FatalError, LoggingHTTPClient
from src.tools.models import EthTransfer

logger = logging.getLogger(__name__)


class BitqueryClient:
    """Bitquery GraphQL API client."""

    def __init__(self, api_key: str = None, timeout: int = 60):
        """
        Initialize Bitquery client.

        Args:
            api_key: Bitquery API key (default: from config.BITQUERY_API_KEY)
            timeout: Request timeout in seconds (default: 60)
        """
        self.api_key = api_key or config.BITQUERY_API_KEY
        if not self.api_key:
            raise ValueError("Bitquery API key required. Set BITQUERY_API_KEY in .env")

        self.graphql_url = "https://streaming.bitquery.io/graphql"

        raw_client = httpx.Client(
            timeout=timeout,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            },
            follow_redirects=True
        )
        self.client = LoggingHTTPClient(raw_client, "bitquery")

    @cached("bitquery")
    @with_retry()
    def _query(self, query: str, variables: Dict[str, Any] = None) -> Dict:
        """
        Execute GraphQL query.

        Args:
            query: GraphQL query string
            variables: Query variables

        Returns:
            Response data

        Raises:
            TransientError: For retryable errors (5xx, timeouts)
            FatalError: For non-retryable errors (4xx, invalid queries)
        """
        payload = {
            "query": query,
            "variables": variables or {}
        }

        response = self.client.post(self.graphql_url, json=payload)

        # Handle HTTP errors
        if response.status_code >= 500:
            raise TransientError(f"Bitquery server error: {response.status_code}")
        if response.status_code == 429:
            # Try to extract Retry-After header (if exists)
            retry_after = response.headers.get('Retry-After')
            if retry_after:
                try:
                    retry_after = float(retry_after)
                except (ValueError, TypeError):
                    retry_after = None
            raise TransientError("Bitquery rate limit exceeded", retry_after=retry_after)
        if response.status_code >= 400:
            raise FatalError(f"Bitquery client error: {response.status_code} - {response.text[:200]}")

        response.raise_for_status()
        data = response.json()

        # Handle GraphQL errors
        if "errors" in data:
            errors = data["errors"]
            error_msg = "; ".join([e.get("message", "Unknown error") for e in errors])
            raise FatalError(f"Bitquery GraphQL error: {error_msg}")

        return data.get("data", {})

    def search_eth_transfers(
        self,
        min_timestamp: int,
        max_timestamp: int,
        min_amount: float = 0,
        max_amount: float = 0,
        from_address: str = None,
        to_address: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Search ETH native transfers by time and amount with automatic pagination.

        Automatically handles pagination for free-tier accounts (10 rows/request limit).
        Continues fetching until reaching the requested limit or no more data available.

        Args:
            min_timestamp: Start time (Unix timestamp)
            max_timestamp: End time (Unix timestamp)
            min_amount: Min transfer amount in ETH (0 = no filter)
            max_amount: Max transfer amount in ETH (0 = no upper bound)
            from_address: Optional sender address filter
            to_address: Optional recipient address filter
            limit: Max total results to return (default 100)

        Returns:
            List of transfer records (auto-paginated up to limit)
        """
        # Convert timestamps to ISO 8601 format
        since = datetime.utcfromtimestamp(min_timestamp).strftime("%Y-%m-%dT%H:%M:%SZ")
        till = datetime.utcfromtimestamp(max_timestamp).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Build WHERE clause dynamically based on filters
        transfer_filters = ["Currency: {Native: true}"]

        # Amount filters
        if min_amount > 0 or max_amount > 0:
            amount_conditions = []
            if min_amount > 0:
                amount_conditions.append(f'ge: "{min_amount}"')
            if max_amount > 0:
                amount_conditions.append(f'le: "{max_amount}"')
            transfer_filters.append(f"Amount: {{{', '.join(amount_conditions)}}}")

        # Address filters
        if from_address:
            transfer_filters.append(f'Sender: {{is: "{from_address}"}}')
        if to_address:
            transfer_filters.append(f'Receiver: {{is: "{to_address}"}}')

        transfer_where = "\n                  ".join(transfer_filters)

        logger.info(f"Bitquery query: time {since} to {till}, "
                    f"amount {min_amount}-{max_amount} ETH, "
                    f"sender={from_address}, receiver={to_address}, limit={limit}")

        # Auto-pagination: fetch until we hit limit or no more data
        all_transfers = []
        offset = 0
        # Free tier limit is 10 rows/request, paid tier can be higher
        # We detect this dynamically based on what API returns
        detected_page_size = None

        while len(all_transfers) < limit:
            # Build GraphQL query with offset
            query = f"""
            query {{
              EVM(network: eth, dataset: archive) {{
                Transfers(
                  limit: {{count: {limit}, offset: {offset}}}
                  where: {{
                    Transfer: {{
                      {transfer_where}
                    }}
                    Block: {{
                      Time: {{since: "{since}", till: "{till}"}}
                    }}
                  }}
                  orderBy: {{descending: Block_Time}}
                ) {{
                  Block {{
                    Number
                    Time
                  }}
                  Transaction {{
                    Hash
                  }}
                  Transfer {{
                    Amount
                    Sender
                    Receiver
                  }}
                }}
              }}
            }}
            """

            logger.debug(f"Fetching with offset={offset}")

            result = self._query(query, {})
            transfers = result.get("EVM", {}).get("Transfers", [])
            returned_count = len(transfers)

            logger.info(f"Bitquery returned {returned_count} transfers at offset {offset}")

            if returned_count == 0:
                # No more data
                logger.info(f"No more transfers available. Total fetched: {len(all_transfers)}")
                break

            all_transfers.extend(transfers)

            # Detect the page size limit from first request
            if detected_page_size is None:
                detected_page_size = returned_count
                logger.info(f"Detected account page size limit: {detected_page_size} rows/request")

            # Check if we need to continue pagination
            # If returned count < detected page size, we've reached the end
            if returned_count < detected_page_size:
                logger.info(f"Received {returned_count} < {detected_page_size}, no more data. "
                           f"Total fetched: {len(all_transfers)}")
                break

            # If returned count == detected page size, there might be more data
            # Continue with next page
            offset += returned_count

        logger.info(f"Total transfers fetched: {len(all_transfers)}")
        if all_transfers:
            logger.debug(f"First transfer sample: {all_transfers[0]}")

        return all_transfers

    def close(self):
        """Close HTTP client."""
        self.client.close()


@tool
def search_eth_transfers_bitquery(
    min_timestamp: int = 0,
    max_timestamp: int = 0,
    min_amount: float = 0,
    max_amount: float = 0,
    limit: int = 100
) -> List[dict]:
    """
    Search ETH native transfers by time and amount (GraphQL API with auto-pagination).

    Supports precise time + amount filtering. Tool handles pagination automatically.
    Amount values in ETH (not wei). Use limit=100 for best results.

    Args:
        min_timestamp: Start time (Unix timestamp), 0 = no lower bound
        max_timestamp: End time (Unix timestamp), 0 = no upper bound
        min_amount: Min amount in ETH, 0 = no filter
        max_amount: Max amount in ETH, 0 = no upper bound
        limit: Total results to return (default 100)

    Returns:
        List[EthTransfer]: Transfers with txid, sender, recipient, amount (ETH), block_time
    """
    if min_timestamp <= 0 and max_timestamp <= 0:
        raise ValueError("At least one of min_timestamp or max_timestamp must be specified")

    client = BitqueryClient()

    try:
        # Get transfers from Bitquery (no address filters for cross-chain tracing)
        raw_transfers = client.search_eth_transfers(
            min_timestamp=min_timestamp,
            max_timestamp=max_timestamp,
            min_amount=min_amount,
            max_amount=max_amount,
            from_address=None,
            to_address=None,
            limit=limit
        )

        # Convert to EthTransfer model
        results = []
        for transfer in raw_transfers:
            block = transfer.get("Block", {})
            transaction = transfer.get("Transaction", {})
            transfer_data = transfer.get("Transfer", {})

            # Parse block time (ISO 8601 format)
            block_time_str = block.get("Time", "")
            try:
                block_time = int(datetime.fromisoformat(block_time_str.replace("Z", "+00:00")).timestamp())
            except (ValueError, AttributeError):
                block_time = 0

            eth_transfer = EthTransfer(
                chain="ETH",
                txid=transaction.get("Hash"),
                status="confirmed",
                sender=transfer_data.get("Sender"),
                recipient=transfer_data.get("Receiver"),
                amount=float(transfer_data.get("Amount", 0)),
                block_time=block_time,
                block_height=block.get("Number"),
                fee=None,  # Bitquery Transfers API doesn't provide fee
                meta={}
            )
            results.append(eth_transfer.model_dump())

        logger.info(f"Found {len(results)} ETH transfers matching criteria")
        return results

    finally:
        client.close()
