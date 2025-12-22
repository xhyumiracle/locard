"""
Binance API tools for historical price queries.

Free, no API key required.
Used for cross-chain value matching (converting coin values to USD).

API Docs: https://developers.binance.com/
"""

from datetime import datetime
from typing import Literal, Optional, List

from langchain_core.tools import tool
from pydantic import BaseModel

from src.tools.base import BaseAPIClient, with_retry, FatalError, TransientError, cached


IntervalType = Literal["1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M"]


class BinanceKline(BaseModel):
    open_time: int          # Unix ms
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int         # Unix ms
    quote_volume: float
    trades: int

    @classmethod
    def from_api_response(cls, data: list) -> "BinanceKline":
        return cls(
            open_time=int(data[0]),
            open=float(data[1]),
            high=float(data[2]),
            low=float(data[3]),
            close=float(data[4]),
            volume=float(data[5]),
            close_time=int(data[6]),
            quote_volume=float(data[7]),
            trades=int(data[8])
        )


class BinanceClient(BaseAPIClient):
    """Binance public API client (free, no auth required)."""

    BASE_URL = "https://api.binance.com"
    SOURCE_NAME = "binance"

    @cached("binance")
    @with_retry()
    def _get_klines_raw(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int],
        end_time: Optional[int],
        limit: int
    ) -> List:
        """Fetch raw kline data (cached)."""
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": min(limit, 1000)
        }
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        response = self.client.get(f"{self.BASE_URL}/api/v3/klines", params=params)
        return self._handle_response(response)

    def get_klines(
        self,
        symbol: str,
        interval: IntervalType = "1d",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 500
    ) -> List[BinanceKline]:
        """
        Fetch Kline/candlestick data (cached).

        Args:
            symbol: Trading pair (e.g., DOGEUSDT, BTCUSDT)
            interval: Kline interval
            start_time: Start time (Unix milliseconds)
            end_time: End time (Unix milliseconds)
            limit: Max results (max 1000)

        Returns:
            List of Kline data
        """
        data = self._get_klines_raw(symbol, interval, start_time, end_time, limit)
        return [BinanceKline.from_api_response(item) for item in data]

    def get_price_at_time(
        self,
        symbol: str,
        timestamp: int
    ) -> tuple[float, bool]:
        """
        Get price at a specific timestamp.

        Args:
            symbol: Trading pair
            timestamp: Unix seconds

        Returns:
            Tuple of (close price, is_inverted) where is_inverted indicates
            if the symbol was flipped (e.g., BTCDOGE -> DOGEBTC)
        """
        timestamp_ms = timestamp * 1000
        is_inverted = False

        # Get klines around the target time
        try:
            klines = self.get_klines(
                symbol=symbol,
                interval="1h",
                start_time=timestamp_ms - 3600000,  # 1 hour before
                end_time=timestamp_ms + 3600000,    # 1 hour after
                limit=3
            )
        except TransientError as e:
            if "400" in str(e):
                # Symbol might not exist, try inverted
                klines = []
            else:
                raise

        if not klines:
            # Try inverted symbol (e.g., BTCDOGE -> DOGEBTC)
            parts = symbol.upper()
            # Common base currencies to try splitting on
            for base in ["BTC", "ETH", "USDT", "USDC", "BUSD", "DOGE"]:
                if parts.endswith(base):
                    coin = parts[:-len(base)]
                    inverted_symbol = f"{base}{coin}"
                    try:
                        klines = self.get_klines(
                            symbol=inverted_symbol,
                            interval="1h",
                            start_time=timestamp_ms - 3600000,
                            end_time=timestamp_ms + 3600000,
                            limit=3
                        )
                        if klines:
                            is_inverted = True
                            break
                    except:
                        continue

        if not klines:
            # Try daily data if hourly not available
            try:
                klines = self.get_klines(
                    symbol=symbol,
                    interval="1d",
                    start_time=timestamp_ms - 86400000,
                    end_time=timestamp_ms + 86400000,
                    limit=3
                )
            except:
                pass

        if not klines:
            raise FatalError(f"No price data for {symbol} at {timestamp}")

        # Find the kline that contains the timestamp
        for kline in klines:
            if kline.open_time <= timestamp_ms <= kline.close_time:
                price = kline.close
                return (1.0 / price if is_inverted else price, is_inverted)

        # Return closest match
        price = klines[0].close
        return (1.0 / price if is_inverted else price, is_inverted)


@tool
def get_historical_price(
    coin: str,
    quote: str = "USDT",
    timestamp: Optional[int] = None
) -> dict:
    """
    Get historical cryptocurrency price at a specific time.

    Args:
        coin: Coin symbol (e.g., DOGE, BTC, ETH)
        quote: Quote currency (default USDT)
        timestamp: Unix seconds timestamp (default: current time)

    Returns:
        Price information at the specified time
    """
    if timestamp is None:
        timestamp = int(datetime.now().timestamp())

    symbol = f"{coin.upper()}{quote.upper()}"
    client = BinanceClient()

    try:
        price, was_inverted = client.get_price_at_time(symbol, timestamp)
        dt = datetime.utcfromtimestamp(timestamp)

        # If inverted, the actual symbol used was reversed
        actual_symbol = f"{quote.upper()}{coin.upper()}" if was_inverted else symbol

        return {
            "success": True,
            "coin": coin.upper(),
            "quote": quote.upper(),
            "symbol": symbol,
            "actual_symbol": actual_symbol,
            "price": price,
            "was_inverted": was_inverted,
            "timestamp": timestamp,
            "datetime_utc": dt.isoformat(),
        }
    except FatalError as e:
        return {
            "success": False,
            "error": str(e),
            "coin": coin.upper(),
            "quote": quote.upper(),
            "timestamp": timestamp,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "coin": coin.upper(),
            "quote": quote.upper(),
            "timestamp": timestamp,
        }


@tool
def get_price_at_timestamp(
    coin: str,
    timestamp: int,
    quote: str = "USDT"
) -> dict:
    """
    Get cryptocurrency price at exact timestamp (for cross-chain value matching).

    Args:
        coin: Coin symbol (DOGE, BTC, ETH, etc.)
        timestamp: Unix seconds timestamp
        quote: Quote currency (default USDT)

    Returns:
        Price and calculated USD value info
    """
    return get_historical_price.invoke({"coin": coin, "quote": quote, "timestamp": timestamp})


def calculate_usd_value(
    amount: float,
    coin: str,
    timestamp: int
) -> Optional[float]:
    """
    Calculate USD value of a coin amount at a specific time.

    Args:
        amount: Amount of coin (in full units, not satoshis)
        coin: Coin symbol
        timestamp: Unix seconds

    Returns:
        USD value or None if price unavailable
    """
    result = get_historical_price.invoke({
        "coin": coin,
        "quote": "USDT",
        "timestamp": timestamp
    })

    if result.get("success") and result.get("price"):
        return amount * result["price"]
    return None
