"""
Celery application for ACU Token Analytics.
Uses Redis as broker (db/1) and result backend (db/2).

Start worker + beat:
    celery -A jobs.celery_app worker --beat --loglevel=info
"""
from celery import Celery
from celery.schedules import crontab

from config import settings

app = Celery(
    "acu_analytics",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Reliability — acknowledge AFTER task completes (not before)
    task_acks_late=True,
    worker_prefetch_multiplier=1,

    # Time limits (seconds)
    task_soft_time_limit=120,   # soft limit — raises SoftTimeLimitExceeded
    task_time_limit=180,        # hard kill after 3 minutes

    # Results expire after 1 hour (we only need recent status)
    result_expires=3600,

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Worker settings — single process is fine for our I/O-bound tasks
    worker_concurrency=2,
)

# Autodiscover tasks in jobs/tasks.py
app.autodiscover_tasks(["jobs"])

# --- Beat schedule (periodic tasks) ---
app.conf.beat_schedule = {
    "sync-swaps-every-15s": {
        "task": "jobs.tasks.sync_swaps_task",
        "schedule": 15.0,
    },
    "sync-transfers-every-30s": {
        "task": "jobs.tasks.sync_transfers_task",
        "schedule": 30.0,
    },
    "aggregate-prices-every-60s": {
        "task": "jobs.tasks.aggregate_prices_task",
        "schedule": 60.0,
    },
    "health-check-every-60s": {
        "task": "jobs.tasks.health_check_task",
        "schedule": 60.0,
    },
}
