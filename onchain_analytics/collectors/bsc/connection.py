"""
BSC Web3 connection manager with fallback RPCs and rate limiting.
"""
import asyncio
import time
from typing import Any, Optional

from web3 import AsyncWeb3, Web3
from requests.exceptions import HTTPError
from web3.exceptions import Web3Exception
from web3.middleware import ExtraDataToPOAMiddleware

from config import settings
from utils.logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Simple rate limiter for RPC calls."""

    def __init__(self, calls_per_second: int = 10):
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self.last_call = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait if necessary to respect rate limit."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_call
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self.last_call = time.monotonic()


class BSCConnection:
    """
    Manages Web3 connections to BSC with automatic failover.
    """

    def __init__(
        self,
        rpc_endpoints: Optional[list[str]] = None,
        rate_limit: int = 10,
    ):
        self.rpc_endpoints = rpc_endpoints or settings.bsc_rpc_endpoints
        self.rate_limiter = RateLimiter(rate_limit)
        self._current_endpoint_idx = 0
        self._w3: Optional[AsyncWeb3] = None
        self._sync_w3: Optional[Web3] = None

    @property
    def current_endpoint(self) -> str:
        """Get current RPC endpoint."""
        return self.rpc_endpoints[self._current_endpoint_idx]

    async def get_web3(self) -> AsyncWeb3:
        """Get async Web3 instance, creating if needed."""
        if self._w3 is None:
            self._w3 = await self._create_async_web3()
        return self._w3

    def get_sync_web3(self) -> Web3:
        """Get synchronous Web3 instance for simple operations."""
        if self._sync_w3 is None:
            self._sync_w3 = self._create_sync_web3()
        return self._sync_w3

    async def _create_async_web3(self) -> AsyncWeb3:
        """Create async Web3 connection."""
        w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.current_endpoint))
        # BSC is a POA chain - need this middleware
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        return w3

    def _create_sync_web3(self) -> Web3:
        """Create synchronous Web3 connection."""
        w3 = Web3(Web3.HTTPProvider(self.current_endpoint))
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        return w3

    async def switch_endpoint(self) -> bool:
        """Switch to next RPC endpoint. Returns False if all exhausted."""
        self._current_endpoint_idx = (self._current_endpoint_idx + 1) % len(self.rpc_endpoints)
        self._w3 = None
        self._sync_w3 = None

        if self._current_endpoint_idx == 0:
            logger.warning("All RPC endpoints exhausted, cycling back to first")
            return False

        logger.info(f"Switched to RPC endpoint: {self.current_endpoint}")
        return True

    async def is_connected(self) -> bool:
        """Check if connected to BSC."""
        try:
            # Use sync web3 as async is_connected() is unreliable
            w3 = self.get_sync_web3()
            return w3.is_connected()
        except Exception:
            return False

    async def get_block_number(self) -> int:
        """Get current block number with rate limiting."""
        await self.rate_limiter.acquire()
        # Use sync web3 for reliability
        w3 = self.get_sync_web3()
        return w3.eth.block_number

    async def get_block(self, block_number: int) -> dict[str, Any]:
        """Get block by number."""
        await self.rate_limiter.acquire()
        w3 = self.get_sync_web3()
        block = w3.eth.get_block(block_number)
        return dict(block)

    async def get_logs(
        self,
        address: str,
        from_block: int,
        to_block: int,
        topics: Optional[list] = None,
    ) -> list[dict]:
        """
        Fetch event logs with automatic retry, backoff, and failover.
        """
        filter_params = {
            "address": Web3.to_checksum_address(address),
            "fromBlock": from_block,
            "toBlock": to_block,
        }
        if topics:
            filter_params["topics"] = topics

        max_retries = 5
        base_delay = 2.0

        for attempt in range(max_retries):
            await self.rate_limiter.acquire()
            w3 = self.get_sync_web3()

            try:
                logs = w3.eth.get_logs(filter_params)
                return [dict(log) for log in logs]
            except (Web3Exception, HTTPError) as e:
                error_msg = str(e)
                logger.warning(f"RPC error (attempt {attempt+1}/{max_retries}) on {self.current_endpoint}: {error_msg}")

                # Check for rate limit errors (RPC -32005 or HTTP 429)
                is_rate_limit = (
                    "limit exceeded" in error_msg.lower()
                    or "-32005" in error_msg
                    or "429" in error_msg
                    or "too many requests" in error_msg.lower()
                )
                if is_rate_limit:
                    delay = base_delay * (2 ** attempt)
                    logger.info(f"Rate limited, waiting {delay}s before retry...")
                    await asyncio.sleep(delay)
                    await self.switch_endpoint()
                elif attempt < max_retries - 1:
                    await self.switch_endpoint()
                    await asyncio.sleep(1)
                else:
                    raise

        return []

    async def call_with_retry(self, func, *args, **kwargs) -> Any:
        """Execute an async web3 call with automatic retry on failure."""
        max_retries = len(self.rpc_endpoints)

        for attempt in range(max_retries):
            try:
                await self.rate_limiter.acquire()
                return await func(*args, **kwargs)
            except Web3Exception as e:
                logger.warning(f"Call failed on {self.current_endpoint}: {e}")
                if attempt < max_retries - 1:
                    await self.switch_endpoint()
                else:
                    raise

    async def health_check(self) -> dict[str, Any]:
        """Run health check on connection."""
        try:
            # Use sync web3 for health check as async is_connected() is unreliable
            w3 = self.get_sync_web3()
            is_connected = w3.is_connected()
            block_number = w3.eth.block_number if is_connected else None
            chain_id = w3.eth.chain_id if is_connected else None

            return {
                "connected": is_connected,
                "endpoint": self.current_endpoint,
                "block_number": block_number,
                "chain_id": chain_id,  # BSC mainnet = 56
                "status": "healthy" if is_connected and chain_id == 56 else "unhealthy",
            }
        except Exception as e:
            return {
                "connected": False,
                "endpoint": self.current_endpoint,
                "error": str(e),
                "status": "unhealthy",
            }


# Global connection instance (use settings for rate limit)
bsc_connection = BSCConnection(rate_limit=settings.rpc_rate_limit)


async def get_bsc() -> BSCConnection:
    """Get BSC connection instance."""
    return bsc_connection
