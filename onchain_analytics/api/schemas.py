"""
Pydantic schemas for API request/response validation.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# ============================================
# Common
# ============================================

class PaginationParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class TimeRangeParams(BaseModel):
    hours: int = Field(default=24, ge=1, le=720)  # Max 30 days


# ============================================
# Price Schemas
# ============================================

class PriceResponse(BaseModel):
    price: float
    timestamp: str
    tx_hash: Optional[str] = None

    class Config:
        from_attributes = True


class OHLCVCandle(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume_usdt: float
    volume_acu: float
    trade_count: int


class PriceHistoryResponse(BaseModel):
    interval: str
    candles: list[OHLCVCandle]
    count: int


class PriceStatsResponse(BaseModel):
    period_hours: int
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    change: Optional[float]
    change_pct: Optional[float]


# ============================================
# Swap Schemas
# ============================================

class SwapResponse(BaseModel):
    tx_hash: str
    timestamp: str
    block_number: int
    type: str  # "buy" or "sell"
    amount_acu: float
    amount_usdt: float
    price_usdt: float
    sender: str
    recipient: str


class SwapsListResponse(BaseModel):
    swaps: list[SwapResponse]
    count: int
    total: Optional[int] = None


# ============================================
# Holder Schemas
# ============================================

class HolderResponse(BaseModel):
    address: str
    balance: float
    percentage: Optional[float] = None
    trade_count: int
    first_seen: str
    last_active: str
    label: Optional[str] = None
    is_contract: Optional[bool] = None


class HoldersListResponse(BaseModel):
    holders: list[HolderResponse]
    count: int
    total_holders: int


class HolderDetailResponse(BaseModel):
    address: str
    balance: float
    total_bought: float
    total_sold: float
    trade_count: int
    first_seen: str
    last_active: str
    avg_buy_price: Optional[float] = None
    label: Optional[str] = None
    is_contract: bool


# ============================================
# Analytics Schemas
# ============================================

class VolumeStats(BaseModel):
    period_hours: int
    volume_usdt: float
    volume_acu: float
    trade_count: int
    unique_buyers: int
    unique_sellers: int


class BuySellStats(BaseModel):
    period_hours: int
    buy_count: int
    sell_count: int
    buy_sell_ratio: Optional[float]
    buy_volume_usdt: float
    sell_volume_usdt: float
    net_flow_usdt: float


class TradeSizeStats(BaseModel):
    period_hours: int
    avg_trade_usdt: float
    median_trade_usdt: float
    min_trade_usdt: float
    max_trade_usdt: float


class MarketOverviewResponse(BaseModel):
    timestamp: str
    price: dict
    volume: dict
    trading: dict
    holders: dict


class HourlyVolumeItem(BaseModel):
    hour: str
    volume_usdt: float
    volume_acu: float
    trade_count: int
    buys: int
    sells: int


# ============================================
# Whale Schemas
# ============================================

class WhaleResponse(BaseModel):
    address: str
    balance: float
    percentage_of_supply: float
    trade_count: int
    first_seen: str
    last_active: str
    label: Optional[str] = None


class WhaleConcentrationResponse(BaseModel):
    total_supply: float
    top_10: dict
    top_50: dict
    whales: dict


class LargeTradeResponse(BaseModel):
    tx_hash: str
    timestamp: str
    type: str
    amount_acu: float
    amount_usdt: float
    price_usdt: float
    sender: str
    recipient: str


class WhaleActivityResponse(BaseModel):
    tx_hash: str
    timestamp: str
    whale_address: str
    action: str
    amount_acu: float
    amount_usdt: float
    price_usdt: float


class WhaleSummaryResponse(BaseModel):
    timestamp: str
    concentration: dict
    top_whales: list[dict]
    activity_24h: dict
    large_trades_24h: list[dict]


# ============================================
# Wallet P&L Schemas
# ============================================

class WalletTradeResponse(BaseModel):
    tx_hash: str
    timestamp: str
    block_number: int
    type: str
    amount_acu: float
    amount_usdt: float
    price_usdt: float


class WalletPnLSummary(BaseModel):
    total_bought_acu: float
    total_bought_usdt: float
    total_sold_acu: float
    total_sold_usdt: float
    current_holdings_acu: float
    avg_buy_price: float


class WalletPnLResult(BaseModel):
    realized_pnl_usdt: float
    unrealized_pnl_usdt: Optional[float]
    total_pnl_usdt: float
    roi_pct: float


class WalletActivity(BaseModel):
    trade_count: int
    buy_count: int
    sell_count: int
    first_trade: Optional[str]
    last_trade: Optional[str]
    holding_days: int


class WalletPnLResponse(BaseModel):
    address: str
    summary: WalletPnLSummary
    pnl: WalletPnLResult
    activity: WalletActivity
    holder_info: dict


# ============================================
# Health Schemas
# ============================================

class HealthResponse(BaseModel):
    status: str
    timestamp: str
    database: str
    bsc_connection: dict
    version: str = "1.0.0"
