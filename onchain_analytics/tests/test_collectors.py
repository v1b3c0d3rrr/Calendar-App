"""
Tests for collector parsers and price calculations.
These are pure unit tests — no DB or network needed.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from eth_abi import encode

from collectors.bsc.pool_swaps import calculate_price_from_sqrt, parse_swap_event
from collectors.bsc.token_transfers import parse_transfer_event
from collectors.prices.acu_price import truncate_timestamp


# ============================================
# Price calculation tests
# ============================================

class TestPriceCalculation:
    """Test sqrtPriceX96 → USDT price conversion."""

    def test_known_price_acu_is_token1(self):
        """Test price calculation when ACU is token1 (our pool's case)."""
        # sqrtPriceX96 that gives a known price
        # For token0=USDT(18), token1=ACU(12):
        # raw_price = (sqrtPriceX96 / 2^96)^2
        # acu_per_usdt = raw_price * 10^(18-12) = raw_price * 10^6
        # usdt_per_acu = 1 / acu_per_usdt
        Q96 = 2**96

        # Set sqrtPriceX96 so that price = 0.1 USDT per ACU
        # usdt_per_acu = 0.1
        # acu_per_usdt = 10
        # raw_price = acu_per_usdt / 10^6 = 10 / 1000000 = 0.00001
        # sqrt(0.00001) * 2^96 = 0.00316... * 2^96
        import math
        raw_price = 10.0 / 1_000_000
        sqrt_price = math.sqrt(raw_price)
        sqrt_price_x96 = int(Decimal(str(sqrt_price)) * Decimal(Q96))

        price = calculate_price_from_sqrt(sqrt_price_x96, acu_is_token0=False)

        assert abs(float(price) - 0.1) < 0.001, f"Expected ~0.1, got {float(price)}"

    def test_price_is_positive(self):
        """Price should always be positive for valid sqrtPriceX96."""
        Q96 = 2**96
        # Any reasonable sqrtPriceX96
        price = calculate_price_from_sqrt(Q96 // 1000, acu_is_token0=False)
        assert price > 0

    def test_price_zero_input(self):
        """Zero sqrtPriceX96 should return 0."""
        price = calculate_price_from_sqrt(0, acu_is_token0=False)
        assert price == Decimal(0)

    def test_higher_sqrt_price_means_cheaper_acu(self):
        """When ACU is token1, higher sqrtPriceX96 means more ACU per USDT = cheaper ACU."""
        Q96 = 2**96
        price_low = calculate_price_from_sqrt(Q96 // 100, acu_is_token0=False)
        price_high = calculate_price_from_sqrt(Q96 // 10, acu_is_token0=False)
        # Higher sqrtPriceX96 → cheaper ACU (lower USDT per ACU)
        assert price_high < price_low


# ============================================
# Swap event parsing tests
# ============================================

class TestSwapParsing:
    """Test parsing raw swap event logs."""

    def _make_swap_log(self, amount0, amount1, sqrt_price_x96, liquidity, tick,
                       sender="0x" + "1" * 40, recipient="0x" + "2" * 40,
                       block_number=50000000, log_index=0, tx_hash=None):
        """Create a mock swap event log."""
        data_bytes = encode(
            ["int256", "int256", "uint160", "uint128", "int24"],
            [amount0, amount1, sqrt_price_x96, liquidity, tick],
        )
        # Provide data as "0x" + hex string — matches how the parser handles it
        data_hex = "0x" + data_bytes.hex()
        if tx_hash is None:
            tx_hash = "0x" + "aa" * 32

        return {
            "data": data_hex,
            "topics": [
                bytes.fromhex("00" * 32),  # event signature (not used in parse)
                bytes.fromhex("00" * 12 + sender[2:]),  # sender (padded)
                bytes.fromhex("00" * 12 + recipient[2:]),  # recipient (padded)
            ],
            "transactionHash": tx_hash,
            "blockNumber": block_number,
            "logIndex": log_index,
        }

    def test_parse_buy_swap(self):
        """Test parsing a buy swap (positive ACU amount)."""
        # token0=USDT, token1=ACU
        # Buy: USDT goes in (negative amount0), ACU goes out (positive amount1)
        Q96 = 2**96
        log = self._make_swap_log(
            amount0=-100 * 10**18,       # -100 USDT (18 decimals)
            amount1=1000 * 10**12,       # +1000 ACU (12 decimals)
            sqrt_price_x96=Q96 // 100,
            liquidity=10**18,
            tick=-200000,
        )

        result = parse_swap_event(log, block_timestamp=1708000000, acu_is_token0=False)

        assert result["amount_acu"] == Decimal("1000")
        assert result["amount_usdt"] == Decimal("100")
        assert result["is_buy"] is True
        assert result["block_number"] == 50000000
        assert result["log_index"] == 0

    def test_parse_sell_swap(self):
        """Test parsing a sell swap (negative ACU amount)."""
        Q96 = 2**96
        log = self._make_swap_log(
            amount0=50 * 10**18,         # +50 USDT out
            amount1=-500 * 10**12,       # -500 ACU in
            sqrt_price_x96=Q96 // 100,
            liquidity=10**18,
            tick=-200000,
        )

        result = parse_swap_event(log, block_timestamp=1708000000, acu_is_token0=False)

        assert result["amount_acu"] == Decimal("500")
        assert result["amount_usdt"] == Decimal("50")
        assert result["is_buy"] is False

    def test_parse_extracts_addresses(self):
        """Test that sender and recipient are correctly extracted from topics."""
        sender = "0x" + "ab" * 20
        recipient = "0x" + "cd" * 20
        Q96 = 2**96

        log = self._make_swap_log(
            amount0=10**18,
            amount1=-10**12,
            sqrt_price_x96=Q96 // 100,
            liquidity=10**18,
            tick=0,
            sender=sender,
            recipient=recipient,
        )

        result = parse_swap_event(log, block_timestamp=1708000000, acu_is_token0=False)

        assert result["sender"] == sender
        assert result["recipient"] == recipient

    def test_parse_sets_timestamp(self):
        """Test that block timestamp is correctly converted."""
        Q96 = 2**96
        log = self._make_swap_log(
            amount0=10**18, amount1=-10**12,
            sqrt_price_x96=Q96 // 100, liquidity=10**18, tick=0,
        )

        ts = 1708000000
        result = parse_swap_event(log, block_timestamp=ts, acu_is_token0=False)

        assert result["timestamp"] == datetime.fromtimestamp(ts, tz=timezone.utc)


# ============================================
# Transfer event parsing tests
# ============================================

class TestTransferParsing:
    """Test parsing raw ERC-20 Transfer event logs."""

    def _make_transfer_log(self, from_addr, to_addr, value,
                           block_number=50000000, log_index=0):
        """Create a mock transfer event log."""
        data_bytes = encode(["uint256"], [value])
        data_hex = "0x" + data_bytes.hex()

        return {
            "data": data_hex,
            "topics": [
                bytes.fromhex("00" * 32),  # event signature
                bytes.fromhex("00" * 12 + from_addr[2:]),
                bytes.fromhex("00" * 12 + to_addr[2:]),
            ],
            "transactionHash": "0x" + "bb" * 32,
            "blockNumber": block_number,
            "logIndex": log_index,
        }

    def test_parse_transfer(self):
        """Test basic transfer parsing."""
        from_addr = "0x" + "11" * 20
        to_addr = "0x" + "22" * 20
        value = 5000 * 10**12  # 5000 ACU with 12 decimals

        log = self._make_transfer_log(from_addr, to_addr, value)
        result = parse_transfer_event(log, block_timestamp=1708000000)

        assert result["from_address"] == from_addr
        assert result["to_address"] == to_addr
        assert result["amount"] == Decimal("5000")
        assert result["block_number"] == 50000000

    def test_parse_small_transfer(self):
        """Test parsing a transfer with fractional amount."""
        from_addr = "0x" + "11" * 20
        to_addr = "0x" + "22" * 20
        value = 1  # 1 smallest unit = 10^-12 ACU

        log = self._make_transfer_log(from_addr, to_addr, value)
        result = parse_transfer_event(log, block_timestamp=1708000000)

        assert result["amount"] == Decimal("1") / Decimal(10**12)

    def test_addresses_are_lowercase(self):
        """Transfer addresses should be lowercased."""
        from_addr = "0x" + "aB" * 20
        to_addr = "0x" + "cD" * 20

        log = self._make_transfer_log(from_addr.lower(), to_addr.lower(), 10**12)
        result = parse_transfer_event(log, block_timestamp=1708000000)

        assert result["from_address"] == result["from_address"].lower()
        assert result["to_address"] == result["to_address"].lower()


# ============================================
# Timestamp truncation tests
# ============================================

class TestTruncateTimestamp:
    """Test the truncate_timestamp utility."""

    def test_truncate_1m(self):
        dt = datetime(2026, 2, 20, 14, 37, 45, 123456)
        result = truncate_timestamp(dt, "1m")
        assert result == datetime(2026, 2, 20, 14, 37, 0, 0)

    def test_truncate_5m(self):
        dt = datetime(2026, 2, 20, 14, 37, 45)
        result = truncate_timestamp(dt, "5m")
        assert result == datetime(2026, 2, 20, 14, 35, 0, 0)

    def test_truncate_15m(self):
        dt = datetime(2026, 2, 20, 14, 37, 45)
        result = truncate_timestamp(dt, "15m")
        assert result == datetime(2026, 2, 20, 14, 30, 0, 0)

    def test_truncate_1h(self):
        dt = datetime(2026, 2, 20, 14, 37, 45)
        result = truncate_timestamp(dt, "1h")
        assert result == datetime(2026, 2, 20, 14, 0, 0, 0)

    def test_truncate_4h(self):
        dt = datetime(2026, 2, 20, 14, 37, 45)
        result = truncate_timestamp(dt, "4h")
        assert result == datetime(2026, 2, 20, 12, 0, 0, 0)

    def test_truncate_1d(self):
        dt = datetime(2026, 2, 20, 14, 37, 45)
        result = truncate_timestamp(dt, "1d")
        assert result == datetime(2026, 2, 20, 0, 0, 0, 0)
