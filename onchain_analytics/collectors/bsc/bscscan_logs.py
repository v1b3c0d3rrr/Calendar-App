"""
BSCScan API client for fetching event logs.

Uses the getLogs endpoint to fetch Swap events by block range.
Advantages over RPC: no tight rate limits, returns timestamps in logs,
paginated responses up to 1000 records per page.

BSCScan free plan: 5 requests/second.
"""
import asyncio
import time

import httpx

from config import settings
from utils.logging import get_logger

logger = get_logger(__name__)

BSCSCAN_API_URL = "https://api.etherscan.io/v2/api"
BSC_CHAIN_ID = 56


class BSCScanClient:
    """HTTP client for BSCScan API with rate limiting and retry."""

    def __init__(
        self,
        api_key: str | None = None,
        rate_limit: int | None = None,
    ):
        self.api_key = api_key or settings.bscscan_api_key
        if not self.api_key or self.api_key == "your_bscscan_api_key_here":
            raise ValueError(
                "BSCSCAN_API_KEY not set. "
                "Get a free key at https://bscscan.com/myapikey "
                "and add it to .env"
            )
        self.rate_limit = rate_limit or settings.bscscan_rate_limit
        self._min_interval = 1.0 / self.rate_limit
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    async def _wait_rate_limit(self) -> None:
        """Enforce rate limit between requests."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_call = time.monotonic()

    async def _request(self, params: dict, max_retries: int = 5) -> dict:
        """Make a BSCScan API request with retry and exponential backoff."""
        params["chainid"] = BSC_CHAIN_ID
        params["apikey"] = self.api_key

        for attempt in range(max_retries):
            await self._wait_rate_limit()

            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(BSCSCAN_API_URL, params=params)
                    resp.raise_for_status()
                    data = resp.json()

                # BSCScan returns status="0" on errors (but also on empty results)
                if data.get("status") == "0" and data.get("message") != "No records found":
                    error_msg = data.get("result", data.get("message", "Unknown error"))
                    # Rate limit hit
                    if "rate limit" in str(error_msg).lower() or "Max rate" in str(error_msg):
                        delay = 2.0 * (2 ** attempt)
                        logger.warning(
                            "BSCScan rate limited, retrying",
                            delay=delay,
                            attempt=attempt + 1,
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise ValueError(f"BSCScan API error: {error_msg}")

                return data

            except httpx.HTTPStatusError as e:
                delay = 2.0 * (2 ** attempt)
                logger.warning(
                    "BSCScan HTTP error, retrying",
                    status=e.response.status_code,
                    delay=delay,
                    attempt=attempt + 1,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                else:
                    raise

            except httpx.RequestError as e:
                delay = 2.0 * (2 ** attempt)
                logger.warning(
                    "BSCScan request error, retrying",
                    error=str(e),
                    delay=delay,
                    attempt=attempt + 1,
                )
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay)
                else:
                    raise

        return {"status": "0", "result": []}

    async def get_logs(
        self,
        address: str,
        topic0: str,
        from_block: int,
        to_block: int,
        page: int = 1,
        offset: int = 1000,
    ) -> list[dict]:
        """
        Fetch event logs from BSCScan.

        Args:
            address: Contract address to filter logs
            topic0: Event signature hash (e.g. Swap topic)
            from_block: Start block number
            to_block: End block number
            page: Page number (1-based)
            offset: Results per page (max 1000)

        Returns:
            List of log dicts with keys: address, topics, data,
            blockNumber, timeStamp, gasPrice, gasUsed, logIndex,
            transactionHash, transactionIndex
        """
        params = {
            "module": "logs",
            "action": "getLogs",
            "address": address,
            "topic0": topic0,
            "fromBlock": from_block,
            "toBlock": to_block,
            "page": page,
            "offset": offset,
        }

        data = await self._request(params)
        result = data.get("result", [])

        # "No records found" returns status="0" but result is a string message
        if isinstance(result, str):
            return []

        return result

    async def get_all_logs(
        self,
        address: str,
        topic0: str,
        from_block: int,
        to_block: int,
        page_size: int = 1000,
    ) -> list[dict]:
        """
        Fetch ALL event logs for a block range, handling pagination.

        BSCScan returns max 1000 logs per page. This method fetches
        all pages until results are exhausted.

        Args:
            address: Contract address
            topic0: Event signature hash
            from_block: Start block
            to_block: End block
            page_size: Results per page (max 1000)

        Returns:
            All matching logs across all pages
        """
        all_logs: list[dict] = []
        page = 1

        while True:
            logs = await self.get_logs(
                address=address,
                topic0=topic0,
                from_block=from_block,
                to_block=to_block,
                page=page,
                offset=page_size,
            )

            if not logs:
                break

            all_logs.extend(logs)

            if len(logs) < page_size:
                # Last page — fewer results than requested
                break

            page += 1
            logger.info(
                "BSCScan pagination",
                page=page,
                logs_so_far=len(all_logs),
                from_block=from_block,
                to_block=to_block,
            )

        return all_logs

    async def get_first_tx_block(self, address: str) -> int | None:
        """
        Find the block of the first transaction for an address.
        Useful for finding pool creation block.
        """
        params = {
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": 1,
            "sort": "asc",
        }

        data = await self._request(params)
        result = data.get("result", [])

        if isinstance(result, str) or not result:
            return None

        return int(result[0]["blockNumber"])
