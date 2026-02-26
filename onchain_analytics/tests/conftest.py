"""
Shared test fixtures for ACU Token Analytics.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from db.models import Base, Holder, Price, Swap, SyncState


# Use the real database for integration tests
# Tests run inside transactions that get rolled back
from config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    poolclass=NullPool,
)

TestSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session():
    """
    Provide a transactional database session for tests.
    Each test gets its own transaction that rolls back after.
    """
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)

        yield session

        await session.close()
        await trans.rollback()


@pytest.fixture
def sample_swaps():
    """Sample swap data for testing."""
    base_time = datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc)

    return [
        Swap(
            tx_hash=f"0x{'f' * 58}test{i:02d}",
            block_number=99000000 + i * 100,
            timestamp=base_time + timedelta(minutes=i * 5),
            log_index=0,
            sender=f"0x{'1' * 40}",
            recipient=f"0x{'2' * 40}",
            amount_acu=Decimal("1000") + Decimal(i) * 100,
            amount_usdt=Decimal("100") + Decimal(i) * 10,
            price_usdt=Decimal("0.1") + Decimal(i) * Decimal("0.001"),
            is_buy=i % 2 == 0,
            sqrt_price_x96=str(2**96),
            liquidity="1000000",
            tick=-200000 + i * 100,
        )
        for i in range(10)
    ]


@pytest.fixture
def sample_holders():
    """Sample holder data for testing."""
    base_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc)

    return [
        Holder(
            address=f"0xtest{'a' * 34}{i:02d}",
            balance=Decimal(str(1000000 // (i + 1))),
            first_seen=base_time,
            last_active=now,
            total_bought=Decimal(str(2000000 // (i + 1))),
            total_sold=Decimal(str(1000000 // (i + 1))),
            trade_count=50 - i * 5,
            avg_buy_price=Decimal("0.1"),
            is_contract=False,
            label=f"Whale {i + 1}" if i < 3 else None,
        )
        for i in range(5)
    ]


@pytest_asyncio.fixture
async def seeded_db(db_session, sample_swaps, sample_holders):
    """Database session pre-seeded with sample data."""
    for swap in sample_swaps:
        db_session.add(swap)
    for holder in sample_holders:
        db_session.add(holder)
    await db_session.flush()
    return db_session
