"""
Analytics API endpoints.
"""
from fastapi import APIRouter, HTTPException, Query

from api.dependencies import TimeRangeDep
from api.schemas import (
    BuySellStats,
    HourlyVolumeItem,
    MarketOverviewResponse,
    TradeSizeStats,
    VolumeStats,
    WalletPnLResponse,
)
from analysis.trading_metrics import (
    get_buy_sell_stats,
    get_hourly_volume,
    get_market_overview,
    get_trade_size_stats,
    get_trading_activity_by_hour,
    get_volume_stats,
)
from analysis.wallet_pnl import (
    calculate_wallet_pnl,
    get_top_losers,
    get_top_profitable_wallets,
    get_wallet_holding_stats,
    get_wallet_trades,
)
from collectors.prices.acu_price import get_current_price

router = APIRouter()


@router.get("/overview", response_model=MarketOverviewResponse)
async def get_overview():
    """
    Get comprehensive market overview.

    Combines price, volume, trading stats, and holder info.
    """
    overview = await get_market_overview()
    return MarketOverviewResponse(**overview)


@router.get("/volume", response_model=VolumeStats)
async def get_volume(time_range: TimeRangeDep):
    """
    Get trading volume statistics.
    """
    stats = await get_volume_stats(time_range["hours"])
    return VolumeStats(**stats)


@router.get("/buy-sell", response_model=BuySellStats)
async def get_buy_sell(time_range: TimeRangeDep):
    """
    Get buy/sell ratio and volume breakdown.
    """
    stats = await get_buy_sell_stats(time_range["hours"])
    return BuySellStats(**stats)


@router.get("/trade-size", response_model=TradeSizeStats)
async def get_trade_size(time_range: TimeRangeDep):
    """
    Get trade size statistics.
    """
    stats = await get_trade_size_stats(time_range["hours"])
    return TradeSizeStats(**stats)


@router.get("/hourly")
async def get_hourly(
    hours: int = Query(default=24, ge=1, le=168, description="Time period"),
):
    """
    Get hourly volume breakdown.
    """
    data = await get_hourly_volume(hours)
    return {"hourly_data": data, "count": len(data)}


@router.get("/activity-pattern")
async def get_activity_pattern():
    """
    Get trading activity pattern by hour of day.

    Useful for identifying peak trading hours.
    """
    data = await get_trading_activity_by_hour()
    return {"activity_by_hour": data}


@router.get("/holding-stats")
async def get_holding_statistics():
    """
    Get aggregate holder statistics and distribution.
    """
    stats = await get_wallet_holding_stats()
    return stats


@router.get("/top-winners")
async def get_top_winners(
    limit: int = Query(default=20, ge=1, le=50),
):
    """
    Get wallets with highest realized P&L.
    """
    wallets = await get_top_profitable_wallets(limit)
    return {"wallets": wallets, "count": len(wallets)}


@router.get("/top-losers")
async def get_top_losing_wallets(
    limit: int = Query(default=20, ge=1, le=50),
):
    """
    Get wallets with worst P&L (biggest losses).
    """
    wallets = await get_top_losers(limit)
    return {"wallets": wallets, "count": len(wallets)}


@router.get("/wallet/{address}")
async def get_wallet_analysis(address: str):
    """
    Get comprehensive analysis for a specific wallet.

    Includes P&L calculation, trade history, and statistics.
    """
    # Get current price for unrealized P&L
    current = await get_current_price()
    current_price = current["price"] if current else None

    pnl = await calculate_wallet_pnl(address, current_price)

    if "error" in pnl:
        raise HTTPException(status_code=404, detail=pnl["error"])

    return pnl


@router.get("/wallet/{address}/trades")
async def get_wallet_trade_history(
    address: str,
    limit: int = Query(default=50, ge=1, le=200),
):
    """
    Get trade history for a wallet.
    """
    trades = await get_wallet_trades(address, limit)
    return {"address": address, "trades": trades, "count": len(trades)}
