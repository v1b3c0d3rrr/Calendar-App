"""
Tests for analysis modules.
These run against the real database using transactional fixtures.
Queries filter by known fixture values to avoid interference from existing data.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import Integer, select, func, case

from db.models import Swap, Holder


# Fixture boundaries (must match conftest.py)
FIXTURE_BASE_TIME = datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc)
FIXTURE_END_TIME = FIXTURE_BASE_TIME + timedelta(minutes=50)
FIXTURE_BLOCK_START = 99000000
FIXTURE_BLOCK_END = 99001000
FIXTURE_ADDR_PREFIX = "0xtest"


# ============================================
# Trading metrics tests
# ============================================

class TestTradingMetrics:

    @pytest.mark.asyncio
    async def test_volume_stats(self, seeded_db):
        """Test volume calculation from fixture swap data."""
        result = await seeded_db.execute(
            select(
                func.sum(Swap.amount_usdt).label("volume"),
                func.count(Swap.id).label("count"),
            ).where(Swap.block_number >= FIXTURE_BLOCK_START)
        )
        row = result.first()

        assert row.count == 10
        # amounts: 100, 110, 120, ..., 190 → sum = 1450
        expected_volume = sum(Decimal("100") + Decimal(i) * 10 for i in range(10))
        assert row.volume == expected_volume

    @pytest.mark.asyncio
    async def test_buy_sell_counts(self, seeded_db):
        """Test buy/sell breakdown. Even indices are buys."""
        result = await seeded_db.execute(
            select(
                func.sum(case((Swap.is_buy == True, 1), else_=0)).label("buys"),
                func.count(Swap.id).label("total"),
            ).where(Swap.block_number >= FIXTURE_BLOCK_START)
        )
        row = result.first()

        # i % 2 == 0 → buys at i=0,2,4,6,8 → 5 buys
        assert int(row.buys) == 5
        assert row.total == 10

    @pytest.mark.asyncio
    async def test_price_range(self, seeded_db):
        """Test price min/max from fixture swap data."""
        result = await seeded_db.execute(
            select(
                func.min(Swap.price_usdt).label("low"),
                func.max(Swap.price_usdt).label("high"),
            ).where(Swap.block_number >= FIXTURE_BLOCK_START)
        )
        row = result.first()

        # Prices: 0.1, 0.101, 0.102, ..., 0.109
        assert row.low == Decimal("0.1")
        assert row.high == Decimal("0.109")

    @pytest.mark.asyncio
    async def test_trade_size_stats(self, seeded_db):
        """Test average trade size calculation."""
        result = await seeded_db.execute(
            select(
                func.avg(Swap.amount_usdt).label("avg"),
                func.min(Swap.amount_usdt).label("min"),
                func.max(Swap.amount_usdt).label("max"),
            ).where(Swap.block_number >= FIXTURE_BLOCK_START)
        )
        row = result.first()

        assert row.min == Decimal("100")
        assert row.max == Decimal("190")
        # Average of 100,110,120,...,190 = 145
        assert float(row.avg) == pytest.approx(145.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_net_flow(self, seeded_db):
        """Test net flow calculation (buy volume - sell volume)."""
        result = await seeded_db.execute(
            select(
                func.sum(
                    case((Swap.is_buy == True, Swap.amount_usdt), else_=Decimal(0))
                ).label("buy_vol"),
                func.sum(
                    case((Swap.is_buy == False, Swap.amount_usdt), else_=Decimal(0))
                ).label("sell_vol"),
            ).where(Swap.block_number >= FIXTURE_BLOCK_START)
        )
        row = result.first()

        buy_vol = float(row.buy_vol)
        sell_vol = float(row.sell_vol)
        # Buys: i=0(100), i=2(120), i=4(140), i=6(160), i=8(180) = 700
        # Sells: i=1(110), i=3(130), i=5(150), i=7(170), i=9(190) = 750
        assert buy_vol == pytest.approx(700.0, rel=0.01)
        assert sell_vol == pytest.approx(750.0, rel=0.01)


# ============================================
# Holder analysis tests
# ============================================

class TestHolderAnalysis:

    @pytest.mark.asyncio
    async def test_holder_count(self, seeded_db):
        """Test counting fixture holders."""
        result = await seeded_db.execute(
            select(func.count(Holder.id)).where(
                Holder.address.like(f"{FIXTURE_ADDR_PREFIX}%")
            )
        )
        count = result.scalar_one()
        assert count == 5

    @pytest.mark.asyncio
    async def test_top_holder_is_biggest(self, seeded_db):
        """Test that top fixture holder has the largest balance."""
        result = await seeded_db.execute(
            select(Holder)
            .where(Holder.address.like(f"{FIXTURE_ADDR_PREFIX}%"))
            .order_by(Holder.balance.desc())
            .limit(1)
        )
        top = result.scalar_one()

        assert top.balance == Decimal("1000000")

    @pytest.mark.asyncio
    async def test_holder_balances_descending(self, seeded_db):
        """Test holders are properly ordered by balance."""
        result = await seeded_db.execute(
            select(Holder.balance)
            .where(Holder.address.like(f"{FIXTURE_ADDR_PREFIX}%"))
            .order_by(Holder.balance.desc())
        )
        balances = [row[0] for row in result.fetchall()]

        # Verify descending order
        for i in range(len(balances) - 1):
            assert balances[i] >= balances[i + 1]

    @pytest.mark.asyncio
    async def test_holder_concentration(self, seeded_db):
        """Test that top 3 holders hold the expected share."""
        result = await seeded_db.execute(
            select(Holder.balance)
            .where(Holder.address.like(f"{FIXTURE_ADDR_PREFIX}%"))
            .where(Holder.balance > 0)
            .order_by(Holder.balance.desc())
        )
        balances = [row[0] for row in result.fetchall()]

        total = sum(balances)
        top3_sum = sum(balances[:3])
        concentration = float(top3_sum / total * 100)

        # Top 3: 1000000, 500000, 333333 out of total ~2283333
        assert concentration > 50  # Top 3 should hold majority

    @pytest.mark.asyncio
    async def test_holder_labels(self, seeded_db):
        """Test that whale labels are set correctly."""
        result = await seeded_db.execute(
            select(Holder).where(
                Holder.address.like(f"{FIXTURE_ADDR_PREFIX}%"),
                Holder.label.isnot(None),
            )
        )
        labeled = result.scalars().all()

        assert len(labeled) == 3  # First 3 have labels
        assert all("Whale" in h.label for h in labeled)


# ============================================
# Whale detection tests
# ============================================

class TestWhaleDetection:

    @pytest.mark.asyncio
    async def test_whale_threshold(self, seeded_db):
        """Test identifying wallets above a balance threshold."""
        threshold = Decimal("400000")
        result = await seeded_db.execute(
            select(Holder)
            .where(
                Holder.address.like(f"{FIXTURE_ADDR_PREFIX}%"),
                Holder.balance >= threshold,
            )
            .order_by(Holder.balance.desc())
        )
        whales = result.scalars().all()

        # Balances: 1000000, 500000, 333333, 250000, 200000
        # Above 400k: 1000000, 500000
        assert len(whales) == 2
        assert whales[0].balance == Decimal("1000000")
        assert whales[1].balance == Decimal("500000")

    @pytest.mark.asyncio
    async def test_all_fixture_holders_have_positive_balance(self, seeded_db):
        """All fixture holders should have positive balance."""
        result = await seeded_db.execute(
            select(func.count(Holder.id)).where(
                Holder.address.like(f"{FIXTURE_ADDR_PREFIX}%"),
                Holder.balance > 0,
            )
        )
        count = result.scalar_one()
        assert count == 5

    @pytest.mark.asyncio
    async def test_whale_trade_counts(self, seeded_db):
        """Test that trade counts are populated correctly."""
        result = await seeded_db.execute(
            select(Holder)
            .where(Holder.address.like(f"{FIXTURE_ADDR_PREFIX}%"))
            .order_by(Holder.balance.desc())
        )
        holders = result.scalars().all()

        # Trade counts: 50, 45, 40, 35, 30 (from fixture)
        assert holders[0].trade_count == 50
        assert holders[-1].trade_count == 30
