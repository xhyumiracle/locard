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
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, List, get_args

from langchain_core.tools import tool
from pydantic import BaseModel
import httpx

from src.clients.base import BaseAPIClient, with_retry, FatalError, TransientError, cached, record_rate_limit
from src.tools.models import PriceRange

logger = logging.getLogger(__name__)


IntervalType = Literal["1s", "1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M"]

# Intermediate quote currencies for price triangulation (in order of preference)
INTERMEDIATE_QUOTES = ["USDT", "USDC", "BTC", "ETH"]

# Invalid symbol cache (persistent, no TTL)
INVALID_SYMBOLS_DIR = Path(".cache/binance_invalid_symbols")


class InvalidSymbolError(FatalError):
    """Raised when a trading pair symbol doesn't exist on Binance."""
    pass


def _is_invalid_symbol(symbol: str) -> bool:
    """Check if symbol is cached as invalid."""
    return (INVALID_SYMBOLS_DIR / symbol).exists()


def _save_invalid_symbol(symbol: str):
    """Mark symbol as invalid by creating a marker file."""
    INVALID_SYMBOLS_DIR.mkdir(parents=True, exist_ok=True)
    (INVALID_SYMBOLS_DIR / symbol).touch()
    logger.info(f"Cached invalid symbol: {symbol}")


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

    def _handle_response(self, response: httpx.Response) -> dict:
        """
        Handle Binance API response with special logic for rate limit bans.

        Responsibility: Error classification ONLY. Does not perform sleep.
        Sleep is handled by @with_retry decorator.

        Binance returns 418 with JSON body containing ban expiry time:
        {"code":-1003,"msg":"Way too much request weight used; IP banned until 1767519478680..."}

        This method parses the ban time and attaches it to TransientError as retry_after.
        """
        if response.status_code == 418:
            record_rate_limit(self.SOURCE_NAME)

            # Try to parse ban time from response body and extract retry_after
            retry_after = None
            try:
                data = response.json()
                msg = data.get("msg", "")
                # Extract timestamp from "IP banned until 1767519478680"
                match = re.search(r"banned until (\d+)", msg)
                if match:
                    ban_until_ms = int(match.group(1))
                    now_ms = int(time.time() * 1000)
                    if ban_until_ms > now_ms:
                        # Calculate wait time but don't sleep here
                        # Let @with_retry handle the actual sleep
                        retry_after = (ban_until_ms - now_ms) / 1000.0
                        logger.debug(
                            f"Binance IP banned until {ban_until_ms} "
                            f"(server suggests {retry_after:.1f}s). "
                            f"Message: {msg}"
                        )
            except (ValueError, KeyError, AttributeError) as e:
                logger.debug(f"Failed to parse ban time from 418 response: {e}")

            # Raise TransientError with retry_after metadata
            # @with_retry will use retry_after if available, otherwise use exponential backoff
            raise TransientError("Rate limit exceeded (418: IP restricted or WAF block)", retry_after=retry_after)

        # Handle 400 errors (bad request)
        if response.status_code == 400:
            try:
                data = response.json()
                error_code = data.get("code")
                if error_code == -1121:  # Invalid symbol
                    msg = data.get("msg", "")
                    logger.info(f"Invalid symbol (code -1121): {msg}")
                    raise InvalidSymbolError(f"{msg}")
            except (ValueError, KeyError):
                pass  # Fall through to base class handling

        # Delegate other status codes to base class
        return super()._handle_response(response)

    @cached("binance")
    @with_retry()
    def _get_klines_raw(
        self,
        symbol: str,
        interval: str,
        start_ts: Optional[int],
        end_ts: Optional[int],
        limit: int
    ) -> List:
        """Fetch raw kline data (cached)."""
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": min(limit, 1000)
        }
        if start_ts:
            params["startTime"] = start_ts
        if end_ts:
            params["endTime"] = end_ts

        response = self.client.get(f"{self.BASE_URL}/api/v3/klines", params=params)
        return self._handle_response(response)

    def get_klines(
        self,
        symbol: str,
        interval: IntervalType = "1d",
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        limit: int = 500
    ) -> List[BinanceKline]:
        """
        Fetch Kline/candlestick data (cached).

        Args:
            symbol: Trading pair (e.g., DOGEUSDT, BTCUSDT)
            interval: Kline interval
            start_ts: Start time (Unix milliseconds)
            end_ts: End time (Unix milliseconds)
            limit: Max results (max 1000)

        Returns:
            List of Kline data
        """
        data = self._get_klines_raw(symbol, interval, start_ts, end_ts, limit)
        return [BinanceKline.from_api_response(item) for item in data]

    def _try_get_klines_for_symbol(
        self,
        symbol: str,
        start_ts_ms: int,
        end_ts_ms: int,
        interval: IntervalType = "1h"
    ) -> Optional[List[BinanceKline]]:
        """
        Try to get klines for a symbol, return None if not found.

        Uses persistent cache to skip known invalid symbols.

        Raises:
            TransientError: Re-raises rate limit errors to stop trying other pairs
            Returns None: Only for FatalError (symbol not found, etc)
        """
        # Check cache first - avoid API call for known invalid symbols
        if _is_invalid_symbol(symbol):
            logger.debug(f"Skipping known invalid symbol: {symbol}")
            return None

        try:
            klines = self.get_klines(
                symbol=symbol,
                interval=interval,
                start_ts=start_ts_ms,
                end_ts=end_ts_ms,
                limit=1000
            )
            return klines if klines else None
        except TransientError:
            # Rate limit or server error - propagate immediately
            # Don't let caller try other pairs/intermediates
            raise
        except InvalidSymbolError:
            # Cache invalid symbol for future calls
            _save_invalid_symbol(symbol)
            return None
        except FatalError:
            # Other fatal errors - don't cache
            return None

    def _get_price_range_direct(
        self,
        coin: str,
        quote: str,
        start_ts_ms: int,
        end_ts_ms: int,
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
        klines = self._try_get_klines_for_symbol(symbol, start_ts_ms, end_ts_ms, interval)
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
        klines = self._try_get_klines_for_symbol(inverted_symbol, start_ts_ms, end_ts_ms, interval)
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
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
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
            start_ts: Start timestamp in seconds (Unix time), None = latest
            end_ts: End timestamp in seconds (Unix time), None = latest
            lower_buffer_perc: Buffer ratio to expand lower bound (e.g., 0.1 means min * 0.9)
            upper_buffer_perc: Buffer ratio to expand upper bound (e.g., 0.1 means max * 1.1)

        Returns:
            {price_min, price_max, via} where via is intermediate if used
        """
        coin = coin.upper()
        quote = quote.upper()

        # Handle time window
        now_ms = int(datetime.now().timestamp() * 1000)
        if start_ts is None and end_ts is None:
            # Latest price: use last hour
            start_ts_ms = now_ms - 1000
            end_ts_ms = now_ms
        else:
            start_ts_ms = (start_ts or 0) * 1000
            end_ts_ms = (end_ts or int(datetime.now().timestamp())) * 1000

        logger.info(f"get_price_range: {coin}/{quote}, time={start_ts}->{end_ts} (ms: {start_ts_ms}->{end_ts_ms})")

        # Same coin = price is 1
        if coin == quote:
            return {
                "price_min": 1.0,
                "price_max": 1.0,
                "via": None
            }

        # Try direct/inverted pair first
        result = self._get_price_range_direct(coin, quote, start_ts_ms, end_ts_ms, interval)
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
            coin_via = self._get_price_range_direct(coin, via, start_ts_ms, end_ts_ms, interval)
            if not coin_via:
                continue

            # Get via/quote price range
            via_quote = self._get_price_range_direct(via, quote, start_ts_ms, end_ts_ms, interval)
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
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
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
            MUST be smaller than (end_ts - start_ts).
            May hit data limit if (end_ts - start_ts)/granularity too large
        start_ts, end_ts: Unix seconds, None = latest/earliest
        if end_ts == start_ts, granularity = 1s
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
        start_ts=start_ts,
        end_ts=end_ts,
        lower_buffer_perc=lower_buffer_perc,
        upper_buffer_perc=upper_buffer_perc,
        interval=granularity  # type: ignore
    )
