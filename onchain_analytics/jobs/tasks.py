"""
Celery tasks wrapping existing async collectors.

Each task bridges async→sync via asyncio.run() since Celery workers
are synchronous. Tasks have automatic retry with exponential backoff.

After each task completes, a signal stores the result in Redis
under acu:task_last:<task_name> so the /jobs/status endpoint can read it.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import redis
from celery.signals import task_postrun

from config import settings
from jobs.celery_app import app
from utils.logging import get_logger

logger = get_logger(__name__)


# --- Signal: store last result per task name in Redis ---

@task_postrun.connect
def store_task_result(sender=None, task_id=None, task=None,
                      retval=None, state=None, **kwargs):
    """Save last task result to Redis for the /jobs/status endpoint."""
    try:
        r = redis.from_url(settings.celery_result_backend, decode_responses=True)
        key = f"acu:task_last:{sender.name}"
        data = {
            "task_id": task_id,
            "state": state,
            "result": retval if isinstance(retval, dict) else str(retval),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
        r.set(key, json.dumps(data), ex=7200)  # expire after 2 hours
    except Exception as e:
        logger.debug(f"Could not store task result: {e}")


def run_async(coro):
    """Bridge async coroutine to sync for Celery workers."""
    return asyncio.run(coro)


# --- Swap sync ---

@app.task(
    bind=True,
    name="jobs.tasks.sync_swaps_task",
    autoretry_for=(Exception,),
    retry_backoff=True,       # exponential: 1s, 2s, 4s...
    retry_backoff_max=60,     # cap at 60 seconds
    max_retries=3,
    acks_late=True,
)
def sync_swaps_task(self):
    """Sync swap events from PancakeSwap V3 pool."""
    from collectors.bsc.pool_swaps import sync_swaps

    logger.info("Starting swap sync task")
    try:
        result = run_async(sync_swaps())
        swaps_saved = result.get("swaps_saved", 0)
        if swaps_saved > 0:
            logger.info(f"Swap sync: {swaps_saved} new swaps saved")
        return {"status": "ok", "swaps_saved": swaps_saved}
    except Exception as exc:
        logger.error(f"Swap sync failed: {exc}", exc_info=True)
        raise


# --- Transfer sync ---

@app.task(
    bind=True,
    name="jobs.tasks.sync_transfers_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
    acks_late=True,
)
def sync_transfers_task(self):
    """Sync ACU token transfer events and update holder balances."""
    from collectors.bsc.token_transfers import sync_transfers

    logger.info("Starting transfer sync task")
    try:
        result = run_async(sync_transfers())
        transfers_saved = result.get("transfers_saved", 0)
        if transfers_saved > 0:
            logger.info(f"Transfer sync: {transfers_saved} new transfers saved")
        return {"status": "ok", "transfers_saved": transfers_saved}
    except Exception as exc:
        logger.error(f"Transfer sync failed: {exc}", exc_info=True)
        raise


# --- Price aggregation ---

@app.task(
    bind=True,
    name="jobs.tasks.aggregate_prices_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
    acks_late=True,
)
def aggregate_prices_task(self):
    """Aggregate swap data into OHLCV price candles (all intervals)."""
    from collectors.prices.acu_price import aggregate_all_intervals

    logger.info("Starting price aggregation task")
    try:
        start_time = datetime.now(timezone.utc) - timedelta(hours=1)
        results = run_async(aggregate_all_intervals(start_time=start_time))
        total = sum(results.values())
        if total > 0:
            logger.info(f"Price aggregation: {total} candles across {results}")
        return {"status": "ok", "candles": dict(results), "total": total}
    except Exception as exc:
        logger.error(f"Price aggregation failed: {exc}", exc_info=True)
        raise


# --- Health check ---

@app.task(
    bind=True,
    name="jobs.tasks.health_check_task",
    max_retries=1,
    acks_late=True,
)
def health_check_task(self):
    """Check BSC connection health and log status."""
    from collectors.bsc.connection import bsc_connection

    try:
        health = run_async(bsc_connection.health_check())
        status = health.get("status", "unknown")
        block = health.get("block_number")
        endpoint = health.get("endpoint", "unknown")

        if status == "healthy":
            logger.info(f"Health OK | Block: {block} | RPC: {endpoint}")
        else:
            logger.warning(f"Health DEGRADED | Status: {status} | RPC: {endpoint}")

        return {
            "status": status,
            "block_number": block,
            "endpoint": endpoint,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error(f"Health check failed: {exc}", exc_info=True)
        return {"status": "error", "error": str(exc)}
