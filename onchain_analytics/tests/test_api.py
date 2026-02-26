"""
Tests for FastAPI endpoints.
Uses httpx AsyncClient with the real app.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app


@pytest.fixture
def client():
    """Create test client."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ============================================
# Root and health endpoints
# ============================================

class TestRootEndpoints:

    @pytest.mark.asyncio
    async def test_root(self, client):
        """Test root endpoint returns API info."""
        async with client as c:
            response = await c.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "ACU Token Analytics API"
        assert data["version"] == "1.0.0"
        assert "endpoints" in data

    @pytest.mark.asyncio
    async def test_health(self, client):
        """Test health endpoint."""
        async with client as c:
            response = await c.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded")
        assert "database" in data
        assert "bsc_connection" in data


# ============================================
# Price endpoints
# ============================================

class TestPriceEndpoints:

    @pytest.mark.asyncio
    async def test_get_price(self, client):
        """Test current price endpoint."""
        async with client as c:
            response = await c.get("/price")
        assert response.status_code == 200
        data = response.json()
        # Price may be null if no swaps in period
        assert "price" in data
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_price_history(self, client):
        """Test price history endpoint."""
        async with client as c:
            response = await c.get("/price/history?interval=1h&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert "interval" in data
        assert data["interval"] == "1h"
        assert "candles" in data
        assert isinstance(data["candles"], list)

    @pytest.mark.asyncio
    async def test_price_history_invalid_interval(self, client):
        """Test that invalid interval returns 422."""
        async with client as c:
            response = await c.get("/price/history?interval=2h")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_24h_stats(self, client):
        """Test 24h stats endpoint."""
        async with client as c:
            response = await c.get("/price/24h")
        assert response.status_code == 200
        data = response.json()
        assert "trade_count" in data
        assert "volume_usdt" in data


# ============================================
# Swaps endpoints
# ============================================

class TestSwapsEndpoints:

    @pytest.mark.asyncio
    async def test_get_swaps(self, client):
        """Test recent swaps endpoint."""
        async with client as c:
            response = await c.get("/swaps?hours=168")
        assert response.status_code == 200
        data = response.json()
        assert "swaps" in data
        assert "count" in data
        assert isinstance(data["swaps"], list)

    @pytest.mark.asyncio
    async def test_swaps_limit(self, client):
        """Test swaps endpoint respects limit."""
        async with client as c:
            response = await c.get("/swaps?hours=168&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["swaps"]) <= 2

    @pytest.mark.asyncio
    async def test_swaps_invalid_hours(self, client):
        """Test that hours > 168 returns 422."""
        async with client as c:
            response = await c.get("/swaps?hours=999")
        assert response.status_code == 422


# ============================================
# Holders endpoints
# ============================================

class TestHoldersEndpoints:

    @pytest.mark.asyncio
    async def test_top_holders(self, client):
        """Test top holders endpoint."""
        async with client as c:
            response = await c.get("/holders/top?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if data:
            assert "address" in data[0]
            assert "balance" in data[0]
            assert "percentage" in data[0]

    @pytest.mark.asyncio
    async def test_holder_count(self, client):
        """Test holder count endpoint."""
        async with client as c:
            response = await c.get("/holders/count")
        assert response.status_code == 200
        data = response.json()
        assert "total_holders" in data
        assert isinstance(data["total_holders"], int)

    @pytest.mark.asyncio
    async def test_holder_distribution(self, client):
        """Test holder distribution endpoint."""
        async with client as c:
            response = await c.get("/holders/distribution")
        assert response.status_code == 200
        data = response.json()
        assert "distribution" in data
        assert isinstance(data["distribution"], list)
        assert len(data["distribution"]) == 5  # 5 tiers


# ============================================
# Analytics endpoints
# ============================================

class TestAnalyticsEndpoints:

    @pytest.mark.asyncio
    async def test_overview(self, client):
        """Test market overview endpoint."""
        async with client as c:
            response = await c.get("/analytics/overview")
        assert response.status_code == 200
        data = response.json()
        assert "price" in data
        assert "volume" in data
        assert "trading" in data
        assert "holders" in data

    @pytest.mark.asyncio
    async def test_volume_stats(self, client):
        """Test volume stats endpoint."""
        async with client as c:
            response = await c.get("/analytics/volume?hours=24")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_buy_sell_stats(self, client):
        """Test buy/sell stats endpoint."""
        async with client as c:
            response = await c.get("/analytics/buy-sell?hours=24")
        assert response.status_code == 200


# ============================================
# Whales endpoints
# ============================================

class TestWhalesEndpoints:

    @pytest.mark.asyncio
    async def test_whale_summary(self, client):
        """Test whale summary endpoint."""
        async with client as c:
            response = await c.get("/whales/summary")
        assert response.status_code == 200
        data = response.json()
        assert "total_whales" in data or "whales" in data or isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_whale_concentration(self, client):
        """Test whale concentration endpoint."""
        async with client as c:
            response = await c.get("/whales/concentration")
        assert response.status_code == 200
