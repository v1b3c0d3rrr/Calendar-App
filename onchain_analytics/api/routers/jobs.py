"""
Jobs monitoring router — shows status of scheduled Celery tasks.
Reads recent task results directly from Redis (no Celery import needed).
"""
import json
from datetime import datetime, timezone

from fastapi import APIRouter

from config import settings
from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# Task names we monitor
MONITORED_TASKS = [
    "jobs.tasks.sync_swaps_task",
    "jobs.tasks.sync_transfers_task",
    "jobs.tasks.aggregate_prices_task",
    "jobs.tasks.health_check_task",
]


def _get_redis_sync():
    """Get a sync Redis connection for reading task results."""
    import redis
    return redis.from_url(settings.celery_result_backend, decode_responses=True)


@router.get("/status")
async def jobs_status():
    """
    Show status of scheduled tasks.
    Reads last result for each task from Redis result backend.
    Returns empty results if Celery worker is not running.
    """
    try:
        r = _get_redis_sync()
        r.ping()
        redis_status = "connected"
    except Exception as e:
        return {
            "redis": "disconnected",
            "error": str(e),
            "tasks": {},
        }

    # Scan for recent task results (celery stores as celery-task-meta-<id>)
    # Instead, we use a simpler approach: store last result per task name
    # in a dedicated key via a Celery signal (see below).
    # For now, show Redis connectivity and basic info.
    tasks_info = {}

    for task_name in MONITORED_TASKS:
        short_name = task_name.split(".")[-1]
        key = f"acu:task_last:{task_name}"
        raw = r.get(key)
        if raw:
            try:
                data = json.loads(raw)
                tasks_info[short_name] = data
            except json.JSONDecodeError:
                tasks_info[short_name] = {"status": "unknown", "raw": raw}
        else:
            tasks_info[short_name] = {"status": "never_run"}

    return {
        "redis": redis_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tasks": tasks_info,
    }
