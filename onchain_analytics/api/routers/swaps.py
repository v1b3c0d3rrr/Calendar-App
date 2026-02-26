"""
Swaps API endpoints.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from api.dependencies import DbSession, PaginationDep
from api.schemas import SwapResponse, SwapsListResponse
from db.models import Swap

router = APIRouter()


@router.get("", response_model=SwapsListResponse)
async def get_swaps(
    db: DbSession,
    pagination: PaginationDep,
    hours: int = Query(default=24, ge=1, le=168, description="Time period"),
    type: Optional[str] = Query(default=None, description="Filter by 'buy' or 'sell'"),
    min_usdt: Optional[float] = Query(default=None, ge=0, description="Min USDT amount"),
    address: Optional[str] = Query(default=None, description="Filter by wallet address"),
):
    """
    Get recent swaps with optional filters.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    query = select(Swap).where(Swap.timestamp >= cutoff)

    if type:
        is_buy = type.lower() == "buy"
        query = query.where(Swap.is_buy == is_buy)

    if min_usdt:
        query = query.where(Swap.amount_usdt >= min_usdt)

    if address:
        addr = address.lower()
        query = query.where((Swap.sender == addr) | (Swap.recipient == addr))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Get paginated results
    query = query.order_by(Swap.timestamp.desc())
    query = query.offset(pagination["offset"]).limit(pagination["limit"])

    result = await db.execute(query)
    swaps = result.scalars().all()

    return SwapsListResponse(
        swaps=[
            SwapResponse(
                tx_hash=s.tx_hash,
                timestamp=s.timestamp.isoformat(),
                block_number=s.block_number,
                type="buy" if s.is_buy else "sell",
                amount_acu=float(s.amount_acu),
                amount_usdt=float(s.amount_usdt),
                price_usdt=float(s.price_usdt),
                sender=s.sender,
                recipient=s.recipient,
            )
            for s in swaps
        ],
        count=len(swaps),
        total=total,
    )


@router.get("/latest")
async def get_latest_swaps(
    db: DbSession,
    limit: int = Query(default=10, ge=1, le=50, description="Number of swaps"),
):
    """
    Get most recent swaps (optimized for live feed).
    """
    result = await db.execute(
        select(Swap).order_by(Swap.timestamp.desc()).limit(limit)
    )
    swaps = result.scalars().all()

    return [
        {
            "tx_hash": s.tx_hash,
            "timestamp": s.timestamp.isoformat(),
            "type": "buy" if s.is_buy else "sell",
            "amount_acu": float(s.amount_acu),
            "amount_usdt": float(s.amount_usdt),
            "price_usdt": float(s.price_usdt),
        }
        for s in swaps
    ]


@router.get("/large")
async def get_large_swaps(
    db: DbSession,
    hours: int = Query(default=24, ge=1, le=168),
    min_usdt: float = Query(default=1000, ge=0, description="Min USDT threshold"),
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Get large swaps (whale trades).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = await db.execute(
        select(Swap)
        .where(Swap.timestamp >= cutoff)
        .where(Swap.amount_usdt >= min_usdt)
        .order_by(Swap.amount_usdt.desc())
        .limit(limit)
    )
    swaps = result.scalars().all()

    return [
        {
            "tx_hash": s.tx_hash,
            "timestamp": s.timestamp.isoformat(),
            "type": "buy" if s.is_buy else "sell",
            "amount_acu": float(s.amount_acu),
            "amount_usdt": float(s.amount_usdt),
            "price_usdt": float(s.price_usdt),
            "sender": s.sender,
            "recipient": s.recipient,
        }
        for s in swaps
    ]
