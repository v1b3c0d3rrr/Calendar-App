"""
SQLAlchemy models for ACU Token Analytics
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Swap(Base):
    """
    Stores all swap events from the ACU/USDT pool.
    TimescaleDB hypertable for efficient time-series queries.
    """
    __tablename__ = "swaps"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Transaction info
    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False, index=True)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Swap participants
    sender: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    recipient: Mapped[str] = mapped_column(String(42), nullable=False, index=True)

    # Amounts (stored as string to preserve precision, or Numeric)
    amount_acu: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    amount_usdt: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)

    # Derived price at swap time
    price_usdt: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)

    # Buy or Sell (from ACU perspective)
    is_buy: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Pool state after swap
    sqrt_price_x96: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    liquidity: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    tick: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_swaps_timestamp", "timestamp"),
        Index("idx_swaps_sender_timestamp", "sender", "timestamp"),
        Index("idx_swaps_block_log", "block_number", "log_index", unique=True),
    )


class Price(Base):
    """
    OHLCV price candles aggregated from swaps.
    Intervals: 1m, 5m, 15m, 1h, 4h, 1d
    """
    __tablename__ = "prices"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Time bucket
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    interval: Mapped[str] = mapped_column(String(10), nullable=False)  # '1m', '5m', '1h', '1d'

    # OHLCV
    open: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)

    # Volume in USDT
    volume_usdt: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)
    volume_acu: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)

    # Trade count
    trade_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("idx_prices_interval_timestamp", "interval", "timestamp"),
        Index("idx_prices_timestamp_interval", "timestamp", "interval", unique=True),
    )


class Holder(Base):
    """
    ACU token holders and their current balances.
    Updated from Transfer events.
    """
    __tablename__ = "holders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    address: Mapped[str] = mapped_column(String(42), nullable=False, unique=True, index=True)

    # Current balance
    balance: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)

    # Statistics
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_active: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Trade stats
    total_bought: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    total_sold: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False, default=0)
    trade_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Average entry price (for P&L calculation)
    avg_buy_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(38, 18), nullable=True)

    # Labels
    is_contract: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        Index("idx_holders_balance", "balance"),
    )


class Transfer(Base):
    """
    ACU token transfer events (ERC-20 Transfer).
    Used to track holder balances.
    """
    __tablename__ = "transfers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    tx_hash: Mapped[str] = mapped_column(String(66), nullable=False, index=True)
    block_number: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    log_index: Mapped[int] = mapped_column(Integer, nullable=False)

    from_address: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    to_address: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)

    __table_args__ = (
        Index("idx_transfers_timestamp", "timestamp"),
        Index("idx_transfers_block_log", "block_number", "log_index", unique=True),
    )


class SyncState(Base):
    """
    Tracks sync progress for incremental data collection.
    """
    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    collector_name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    last_block: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )

    # Additional state info (JSON serialized)
    extra_state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
