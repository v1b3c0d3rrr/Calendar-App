"""
Price API endpoints.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from api.schemas import (
    OHLCVCandle,
    PriceHistoryResponse,
    PriceResponse,
    PriceStatsResponse,
)
from collectors.prices.acu_price import (
    get_24h_stats,
    get_candles,
    get_current_price,
)
from analysis.trading_metrics import get_price_stats

router = APIRouter()


@router.get("", response_model=PriceResponse)
async def get_price():
    """
    Get current ACU price.

    Returns the most recent price from swap data.
    """
    price = await get_current_price()
    if not price:
        raise HTTPException(status_code=404, detail="No price data available")

    return PriceResponse(
        price=price["price"],
        timestamp=price["timestamp"],
        tx_hash=price.get("tx_hash"),
    )


@router.get("/stats", response_model=PriceStatsResponse)
async def get_price_statistics(
    hours: int = Query(default=24, ge=1, le=168, description="Time period in hours"),
):
    """
    Get price statistics for a time period.

    Returns open, high, low, close, and price change.
    """
    stats = await get_price_stats(hours)

    return PriceStatsResponse(**stats)


@router.get("/history", response_model=PriceHistoryResponse)
async def get_price_history(
    interval: str = Query(
        default="1h",
        description="Candle interval",
        pattern="^(1m|5m|15m|1h|4h|1d)$",
    ),
    limit: int = Query(default=100, ge=1, le=1000, description="Number of candles"),
    start: Optional[str] = Query(default=None, description="Start time (ISO format)"),
    end: Optional[str] = Query(default=None, description="End time (ISO format)"),
):
    """
    Get OHLCV price history candles.

    Supported intervals: 1m, 5m, 15m, 1h, 4h, 1d
    """
    start_time = None
    end_time = None

    if start:
        try:
            start_time = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start time format")

    if end:
        try:
            end_time = datetime.fromisoformat(end.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end time format")

    candles = await get_candles(
        interval=interval,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
    )

    return PriceHistoryResponse(
        interval=interval,
        candles=[OHLCVCandle(**c) for c in candles],
        count=len(candles),
    )


@router.get("/24h")
async def get_24h_summary():
    """
    Get 24-hour price and volume summary.
    """
    stats = await get_24h_stats()
    return stats
