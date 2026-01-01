"""
Binance API tools for historical price queries.

Free, no API key required.
Used for cross-chain amount matching (converting coin amounts to USD).

Price Direction Convention:
- get_price_range(coin, quote) returns price where: 1 coin = price quote
- Example: get_price_range("DOGE", "BTC") returns how many BTC per 1 DOGE

API Docs: https://developers.binance.com/
"""

import logging
from datetime import datetime
from typing import Literal, Optional, List, get_args

from langchain_core.tools import tool
from pydantic import BaseModel

from src.tools.base import BaseAPIClient, with_retry, FatalError, TransientError, cached
from src.tools.models import PriceRange

logger = logging.getLogger(__name__)


IntervalType = Literal["1s", "1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M"]

# Intermediate quote currencies for price triangulation (in order of preference)
INTERMEDIATE_QUOTES = ["USDT", "USDC", "BTC", "ETH"]


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

    def _try_get_klines_for_symbol(
        self,
        symbol: str,
        start_time_ms: int,
        end_time_ms: int,
        interval: IntervalType = "1h"
    ) -> Optional[List[BinanceKline]]:
        """Try to get klines for a symbol, return None if not found."""
        try:
            klines = self.get_klines(
                symbol=symbol,
                interval=interval,
                start_time=start_time_ms,
                end_time=end_time_ms,
                limit=1000
            )
            return klines if klines else None
        except (TransientError, FatalError):
            return None

    def _get_price_range_direct(
        self,
        coin: str,
        quote: str,
        start_time_ms: int,
        end_time_ms: int,
        interval: IntervalType = "1h"
    ) -> Optional[dict]:
        """
        Try to get price range directly or via inversion.

        Returns:
            {"price_min": float, "price_max": float} or None
        """
        coin = coin.upper()
        quote = quote.upper()

        # Try direct symbol: COINQUOTE (e.g., DOGEBTC)
        symbol = f"{coin}{quote}"
        logger.info(f"Trying direct symbol: {symbol} (interval={interval})")
        klines = self._try_get_klines_for_symbol(symbol, start_time_ms, end_time_ms, interval)
        if klines:
            lows = [k.low for k in klines]
            highs = [k.high for k in klines]
            logger.info(f"Direct {symbol}: got {len(klines)} klines, min={min(lows)}, max={max(highs)}")
            return {
                "price_min": min(lows),
                "price_max": max(highs),
            }
        else:
            logger.info(f"Direct {symbol}: no klines returned")

        # Try inverted symbol: QUOTECOIN (e.g., BTCDOGE)
        inverted_symbol = f"{quote}{coin}"
        logger.info(f"Trying inverted symbol: {inverted_symbol}")
        klines = self._try_get_klines_for_symbol(inverted_symbol, start_time_ms, end_time_ms, interval)
        if klines:
            # Invert: 1/high becomes new low, 1/low becomes new high
            lows = [k.low for k in klines]
            highs = [k.high for k in klines]
            logger.info(f"Inverted {inverted_symbol}: got {len(klines)} klines, inverted min={1.0/max(highs)}, max={1.0/min(lows)}")
            return {
                "price_min": 1.0 / max(highs),  # 1/max(high) = min inverted price
                "price_max": 1.0 / min(lows),   # 1/min(low) = max inverted price
            }
        else:
            logger.info(f"Inverted {inverted_symbol}: no klines returned")

        return None

    def get_price_range(
        self,
        coin: str,
        quote: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        lower_buffer_perc: float = 0,
        upper_buffer_perc: float = 0,
        interval: IntervalType = "1h"
    ) -> PriceRange:
        """
        Get price range for coin/quote pair over a time window.

        Price direction: 1 coin = X quote (e.g., DOGE/BTC means 1 DOGE = X BTC)

        If direct pair not available, tries:
        1. Inverted pair (quote/coin) and inverts the price
        2. Intermediate quote triangulation (coin/USDT * USDT/quote)

        Args:
            coin: Base coin (e.g., "DOGE")
            quote: Quote currency (e.g., "BTC")
            start_time: Start time (Unix seconds), None = latest
            end_time: End time (Unix seconds), None = latest
            lower_buffer_perc: Buffer ratio to expand lower bound (e.g., 0.1 means min * 0.9)
            upper_buffer_perc: Buffer ratio to expand upper bound (e.g., 0.1 means max * 1.1)

        Returns:
            {price_min, price_max, via} where via is intermediate if used
        """
        coin = coin.upper()
        quote = quote.upper()

        # Handle time window
        now_ms = int(datetime.now().timestamp() * 1000)
        if start_time is None and end_time is None:
            # Latest price: use last hour
            start_time_ms = now_ms - 1000
            end_time_ms = now_ms
        else:
            start_time_ms = (start_time or 0) * 1000
            end_time_ms = (end_time or int(datetime.now().timestamp())) * 1000

        logger.info(f"get_price_range: {coin}/{quote}, time={start_time}->{end_time} (ms: {start_time_ms}->{end_time_ms})")

        # Same coin = price is 1
        if coin == quote:
            return {
                "price_min": 1.0,
                "price_max": 1.0,
                "via": None
            }

        # Try direct/inverted pair first
        result = self._get_price_range_direct(coin, quote, start_time_ms, end_time_ms, interval)
        if result:
            price_min = result["price_min"]
            price_max = result["price_max"]
            # Apply buffers (buffer_perc is ratio, e.g., 0.1 = 10%)
            if lower_buffer_perc > 0:
                price_min = price_min * (1 - lower_buffer_perc)
            if upper_buffer_perc > 0:
                price_max = price_max * (1 + upper_buffer_perc)
            return {
                "price_min": price_min,
                "price_max": price_max,
                "via": None
            }

        # Try intermediate quote triangulation
        for via in INTERMEDIATE_QUOTES:
            if via == coin or via == quote:
                continue

            # Get coin/via price range
            coin_via = self._get_price_range_direct(coin, via, start_time_ms, end_time_ms, interval)
            if not coin_via:
                continue

            # Get via/quote price range
            via_quote = self._get_price_range_direct(via, quote, start_time_ms, end_time_ms, interval)
            if not via_quote:
                continue

            # Multiply ranges: [a_min, a_max] * [b_min, b_max]
            # Min = a_min * b_min, Max = a_max * b_max
            price_min = coin_via["price_min"] * via_quote["price_min"]
            price_max = coin_via["price_max"] * via_quote["price_max"]

            # Apply buffers (buffer_perc is ratio, e.g., 0.1 = 10%)
            if lower_buffer_perc > 0:
                price_min = price_min * (1 - lower_buffer_perc)
            if upper_buffer_perc > 0:
                price_max = price_max * (1 + upper_buffer_perc)

            return {
                "price_min": price_min,
                "price_max": price_max,
                "via": via
            }

        raise FatalError(f"No price data for {coin}/{quote} (tried direct, inverted, and intermediates)")


@tool
def get_price_binance(
    coin: str,
    quote: str,
    granularity: str,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    lower_buffer_perc: float = 0,
    upper_buffer_perc: float = 0,
) -> PriceRange:
    """
    Get price range for a trading pair over a time window. Free API.

    Returns price where: 1 <coin> = X <quote>

    Handles unavailable pairs by:
    1. Trying inverted pair and inverting the price
    2. Using intermediate quote triangulation

    Args:
        coin: The coin to price (e.g., "DOGE", "BTC")
        quote: The quote currency (e.g., "BTC", "USDT"). Result tells how much quote per 1 coin.
        granularity: Kline interval ("1s", "1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M").
            MUST be smaller than (end_time - start_time).
            May hit data limit if (end_time - start_time)/granularity too large
        start_time, end_time: Unix seconds, None = latest/earliest
        if end_time == start_time, granularity = 1s
        lower_buffer_perc: Buffer ratio to expand lower bound (e.g., 0.1 means min * 0.9)
        upper_buffer_perc: Buffer ratio to expand upper bound (e.g., 0.1 means max * 1.1)

    Returns:
        {price_min, price_max, via}
    """
    if granularity not in get_args(IntervalType):
        raise ValueError(f"Invalid granularity: {granularity}. Use one of {get_args(IntervalType)}")

    coin = coin.upper()
    quote = quote.upper()

    client = BinanceClient()
    return client.get_price_range(
        coin=coin,
        quote=quote,
        start_time=start_time,
        end_time=end_time,
        lower_buffer_perc=lower_buffer_perc,
        upper_buffer_perc=upper_buffer_perc,
        interval=granularity  # type: ignore
    )
