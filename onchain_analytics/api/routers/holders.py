"""
Holders API endpoints.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from api.dependencies import DbSession, PaginationDep
from api.schemas import HolderDetailResponse, HolderResponse, HoldersListResponse
from collectors.bsc.token_transfers import get_holder_stats, get_top_holders
from db.models import Holder

router = APIRouter()


@router.get("", response_model=HoldersListResponse)
async def get_holders(
    db: DbSession,
    pagination: PaginationDep,
    min_balance: Optional[float] = Query(default=None, ge=0, description="Min balance filter"),
    sort: str = Query(default="balance", description="Sort by: balance, trade_count, last_active"),
):
    """
    Get ACU token holders.
    """
    # Get total holder count
    count_result = await db.execute(
        select(func.count(Holder.id)).where(Holder.balance > 0)
    )
    total_holders = count_result.scalar_one()

    # Get total supply for percentage
    supply_result = await db.execute(
        select(func.sum(Holder.balance)).where(Holder.balance > 0)
    )
    total_supply = supply_result.scalar_one() or 1

    # Build query
    query = select(Holder).where(Holder.balance > 0)

    if min_balance:
        query = query.where(Holder.balance >= min_balance)

    # Sort
    if sort == "trade_count":
        query = query.order_by(Holder.trade_count.desc())
    elif sort == "last_active":
        query = query.order_by(Holder.last_active.desc())
    else:
        query = query.order_by(Holder.balance.desc())

    query = query.offset(pagination["offset"]).limit(pagination["limit"])

    result = await db.execute(query)
    holders = result.scalars().all()

    return HoldersListResponse(
        holders=[
            HolderResponse(
                address=h.address,
                balance=float(h.balance),
                percentage=float(h.balance / total_supply * 100),
                trade_count=h.trade_count,
                first_seen=h.first_seen.isoformat(),
                last_active=h.last_active.isoformat(),
                label=h.label,
                is_contract=h.is_contract,
            )
            for h in holders
        ],
        count=len(holders),
        total_holders=total_holders,
    )


@router.get("/top")
async def get_top_token_holders(
    limit: int = Query(default=20, ge=1, le=100, description="Number of holders"),
):
    """
    Get top ACU holders by balance.
    """
    holders = await get_top_holders(limit)
    return holders


@router.get("/count")
async def get_holder_count(db: DbSession):
    """
    Get total number of holders.
    """
    result = await db.execute(
        select(func.count(Holder.id)).where(Holder.balance > 0)
    )
    count = result.scalar_one()

    return {"total_holders": count}


@router.get("/distribution")
async def get_holder_distribution(db: DbSession):
    """
    Get holder distribution by balance tiers.
    """
    # Define tiers
    tiers = [
        ("dust", 0, 100),
        ("small", 100, 1000),
        ("medium", 1000, 10000),
        ("large", 10000, 100000),
        ("whale", 100000, None),
    ]

    distribution = []
    for tier_name, min_bal, max_bal in tiers:
        query = select(
            func.count(Holder.id).label("count"),
            func.sum(Holder.balance).label("total"),
        ).where(Holder.balance >= min_bal)

        if max_bal:
            query = query.where(Holder.balance < max_bal)

        result = await db.execute(query)
        row = result.first()

        distribution.append({
            "tier": tier_name,
            "min_balance": min_bal,
            "max_balance": max_bal,
            "holder_count": row.count or 0,
            "total_balance": float(row.total or 0),
        })

    return {"distribution": distribution}


@router.get("/{address}", response_model=HolderDetailResponse)
async def get_holder_detail(address: str):
    """
    Get detailed information for a specific holder.
    """
    stats = await get_holder_stats(address)

    if not stats:
        raise HTTPException(status_code=404, detail="Holder not found")

    return HolderDetailResponse(
        address=stats["address"],
        balance=stats["balance"],
        total_bought=stats["total_bought"],
        total_sold=stats["total_sold"],
        trade_count=stats["trade_count"],
        first_seen=stats["first_seen"],
        last_active=stats["last_active"],
        avg_buy_price=stats["avg_buy_price"],
        label=stats["label"],
        is_contract=stats["is_contract"] or False,
    )
