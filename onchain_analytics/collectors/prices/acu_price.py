"""
ACU price calculator and OHLCV aggregator.
Aggregates swap data into price candles.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Integer, func, select, text
from sqlalchemy.dialects.postgresql import insert

from db.database import get_db_session
from db.models import Price, Swap
from utils.logging import get_logger

logger = get_logger(__name__)

# Supported intervals with their timedelta
INTERVALS = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


def truncate_timestamp(dt: datetime, interval: str) -> datetime:
    """Truncate timestamp to interval boundary."""
    if interval == "1m":
        return dt.replace(second=0, microsecond=0)
    elif interval == "5m":
        return dt.replace(minute=(dt.minute // 5) * 5, second=0, microsecond=0)
    elif interval == "15m":
        return dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)
    elif interval == "1h":
        return dt.replace(minute=0, second=0, microsecond=0)
    elif interval == "4h":
        return dt.replace(hour=(dt.hour // 4) * 4, minute=0, second=0, microsecond=0)
    elif interval == "1d":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return dt


async def get_current_price() -> Optional[dict]:
    """Get the most recent ACU price from swaps."""
    async with get_db_session() as session:
        result = await session.execute(
            select(Swap.price_usdt, Swap.timestamp, Swap.tx_hash)
            .order_by(Swap.timestamp.desc())
            .limit(1)
        )
        row = result.first()
        if row:
            return {
                "price": float(row.price_usdt),
                "timestamp": row.timestamp.isoformat(),
                "tx_hash": row.tx_hash,
            }
        return None


async def get_24h_stats() -> dict:
    """Get 24-hour trading statistics."""
    async with get_db_session() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        result = await session.execute(
            select(
                func.count(Swap.id).label("trade_count"),
                func.sum(Swap.amount_usdt).label("volume_usdt"),
                func.sum(Swap.amount_acu).label("volume_acu"),
                func.count(func.distinct(Swap.sender)).label("unique_traders"),
                func.sum(func.cast(Swap.is_buy, type_=Integer)).label("buys"),
            ).where(Swap.timestamp >= cutoff)
        )
        row = result.first()

        # Get price change
        price_result = await session.execute(
            select(Swap.price_usdt)
            .where(Swap.timestamp >= cutoff)
            .order_by(Swap.timestamp.asc())
            .limit(1)
        )
        first_price = price_result.scalar_one_or_none()

        current = await get_current_price()
        current_price = Decimal(str(current["price"])) if current else None

        price_change_pct = None
        if first_price and current_price:
            price_change_pct = float((current_price - first_price) / first_price * 100)

        return {
            "trade_count": row.trade_count or 0,
            "volume_usdt": float(row.volume_usdt or 0),
            "volume_acu": float(row.volume_acu or 0),
            "unique_traders": row.unique_traders or 0,
            "buys": int(row.buys or 0),
            "sells": (row.trade_count or 0) - int(row.buys or 0),
            "price_change_24h_pct": price_change_pct,
            "current_price": float(current_price) if current_price else None,
        }


async def aggregate_candles(
    interval: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> int:
    """
    Aggregate swaps into OHLCV candles for the given interval.

    Uses TimescaleDB time_bucket for efficient aggregation.
    """
    if interval not in INTERVALS:
        raise ValueError(f"Invalid interval: {interval}. Must be one of {list(INTERVALS.keys())}")

    async with get_db_session() as session:
        # Build bucket expression using standard PostgreSQL
        # date_trunc works for 1m, 1h, 1d; custom floor for 5m, 15m, 4h
        bucket_expr = {
            "1m": "date_trunc('minute', timestamp)",
            "5m": "date_trunc('hour', timestamp) + INTERVAL '5 min' * FLOOR(EXTRACT(MINUTE FROM timestamp) / 5)",
            "15m": "date_trunc('hour', timestamp) + INTERVAL '15 min' * FLOOR(EXTRACT(MINUTE FROM timestamp) / 15)",
            "1h": "date_trunc('hour', timestamp)",
            "4h": "date_trunc('day', timestamp) + INTERVAL '4 hours' * FLOOR(EXTRACT(HOUR FROM timestamp) / 4)",
            "1d": "date_trunc('day', timestamp)",
        }[interval]

        query = f"""
            SELECT
                {bucket_expr} AS bucket,
                (array_agg(price_usdt ORDER BY timestamp ASC))[1] AS open,
                MAX(price_usdt) AS high,
                MIN(price_usdt) AS low,
                (array_agg(price_usdt ORDER BY timestamp DESC))[1] AS close,
                SUM(amount_usdt) AS volume_usdt,
                SUM(amount_acu) AS volume_acu,
                COUNT(*) AS trade_count
            FROM swaps
            WHERE 1=1
        """

        params = {}
        if start_time:
            query += " AND timestamp >= :start_time"
            params["start_time"] = start_time
        if end_time:
            query += " AND timestamp < :end_time"
            params["end_time"] = end_time

        query += """
            GROUP BY bucket
            ORDER BY bucket
        """

        result = await session.execute(text(query), params)
        rows = result.fetchall()

        if not rows:
            return 0

        # Prepare candle records
        candles = []
        for row in rows:
            candles.append({
                "timestamp": row.bucket,
                "interval": interval,
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume_usdt": row.volume_usdt,
                "volume_acu": row.volume_acu,
                "trade_count": row.trade_count,
            })

        # Upsert candles
        stmt = insert(Price).values(candles)
        stmt = stmt.on_conflict_do_update(
            index_elements=["timestamp", "interval"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume_usdt": stmt.excluded.volume_usdt,
                "volume_acu": stmt.excluded.volume_acu,
                "trade_count": stmt.excluded.trade_count,
            },
        )
        await session.execute(stmt)
        await session.commit()

        logger.info(f"Aggregated {len(candles)} {interval} candles")
        return len(candles)


async def get_candles(
    interval: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    limit: int = 100,
) -> list[dict]:
    """Fetch OHLCV candles from database."""
    async with get_db_session() as session:
        query = (
            select(Price)
            .where(Price.interval == interval)
            .order_by(Price.timestamp.desc())
            .limit(limit)
        )

        if start_time:
            query = query.where(Price.timestamp >= start_time)
        if end_time:
            query = query.where(Price.timestamp < end_time)

        result = await session.execute(query)
        prices = result.scalars().all()

        return [
            {
                "timestamp": p.timestamp.isoformat(),
                "open": float(p.open),
                "high": float(p.high),
                "low": float(p.low),
                "close": float(p.close),
                "volume_usdt": float(p.volume_usdt),
                "volume_acu": float(p.volume_acu),
                "trade_count": p.trade_count,
            }
            for p in reversed(prices)  # Return chronological order
        ]


async def aggregate_all_intervals(
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> dict[str, int]:
    """Aggregate candles for all intervals."""
    results = {}
    for interval in INTERVALS:
        count = await aggregate_candles(interval, start_time, end_time)
        results[interval] = count
    return results


async def run_aggregation_loop(interval_seconds: int = 60) -> None:
    """Run continuous aggregation loop."""
    logger.info("Starting price aggregation loop...")

    while True:
        try:
            # Aggregate last hour of data for all intervals
            start_time = datetime.now(timezone.utc) - timedelta(hours=1)
            results = await aggregate_all_intervals(start_time=start_time)
            logger.info(f"Aggregation complete: {results}")
        except Exception as e:
            logger.error(f"Aggregation error: {e}")

        await asyncio.sleep(interval_seconds)


# CLI entry point
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    async def main():
        if len(sys.argv) > 1:
            if sys.argv[1] == "--continuous":
                await run_aggregation_loop()
            elif sys.argv[1] == "--stats":
                stats = await get_24h_stats()
                print(f"24h Stats: {stats}")
            elif sys.argv[1] == "--price":
                price = await get_current_price()
                print(f"Current Price: {price}")
        else:
            # One-time aggregation
            results = await aggregate_all_intervals()
            print(f"Aggregation complete: {results}")

    asyncio.run(main())
