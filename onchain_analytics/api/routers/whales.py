"""
Whale tracking API endpoints.
"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Query

from api.schemas import (
    LargeTradeResponse,
    WhaleActivityResponse,
    WhaleConcentrationResponse,
    WhaleResponse,
    WhaleSummaryResponse,
)
from analysis.whales import (
    get_accumulation_wallets,
    get_distribution_wallets,
    get_large_trades,
    get_whale_activity,
    get_whale_concentration,
    get_whale_summary,
    get_whale_transfers,
    get_whales,
)

router = APIRouter()


@router.get("")
async def get_whale_list(
    min_balance: Optional[float] = Query(default=100000, ge=0, description="Min balance to be whale"),
    limit: int = Query(default=50, ge=1, le=100),
):
    """
    Get list of whale wallets.
    """
    whales = await get_whales(
        min_balance=Decimal(str(min_balance)) if min_balance else None,
        limit=limit,
    )
    return {"whales": whales, "count": len(whales)}


@router.get("/summary", response_model=WhaleSummaryResponse)
async def get_whale_overview():
    """
    Get comprehensive whale analysis summary.
    """
    summary = await get_whale_summary()
    return WhaleSummaryResponse(**summary)


@router.get("/concentration", response_model=WhaleConcentrationResponse)
async def get_concentration():
    """
    Get whale concentration metrics.

    Shows percentage of supply held by top 10, top 50, and whales.
    """
    concentration = await get_whale_concentration()
    return WhaleConcentrationResponse(**concentration)


@router.get("/activity")
async def get_whale_trades(
    hours: int = Query(default=24, ge=1, le=168),
):
    """
    Get recent trading activity from whale wallets.
    """
    activity = await get_whale_activity(hours)
    return {"activity": activity, "count": len(activity)}


@router.get("/large-trades")
async def get_large_trade_list(
    hours: int = Query(default=24, ge=1, le=168),
    min_usdt: float = Query(default=1000, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Get large trades (potential whale activity).
    """
    trades = await get_large_trades(
        hours=hours,
        min_usdt=Decimal(str(min_usdt)),
        limit=limit,
    )
    return {"trades": trades, "count": len(trades)}


@router.get("/transfers")
async def get_large_transfers(
    hours: int = Query(default=24, ge=1, le=168),
    min_amount: float = Query(default=10000, ge=0, description="Min ACU amount"),
):
    """
    Get large token transfers (wallet-to-wallet movements).
    """
    transfers = await get_whale_transfers(
        hours=hours,
        min_amount=Decimal(str(min_amount)),
    )
    return {"transfers": transfers, "count": len(transfers)}


@router.get("/accumulating")
async def get_accumulators(
    days: int = Query(default=7, ge=1, le=30, description="Time period in days"),
):
    """
    Get wallets that have been accumulating (net buyers).
    """
    wallets = await get_accumulation_wallets(days)
    return {"wallets": wallets, "count": len(wallets)}


@router.get("/distributing")
async def get_distributors(
    days: int = Query(default=7, ge=1, le=30, description="Time period in days"),
):
    """
    Get wallets that have been distributing (net sellers).
    """
    wallets = await get_distribution_wallets(days)
    return {"wallets": wallets, "count": len(wallets)}
