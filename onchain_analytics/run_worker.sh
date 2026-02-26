#!/bin/bash
# Start Celery worker + beat scheduler for ACU Analytics.
#
# Usage:
#   ./run_worker.sh              — worker + beat (default)
#   ./run_worker.sh worker       — worker only (no scheduler)
#   ./run_worker.sh beat         — beat only (no worker)
#   ./run_worker.sh flower       — Flower web monitor (localhost:5555)
#
# Prerequisites:
#   - Redis running: brew services start redis
#   - Virtual env active: source venv/bin/activate

set -e

cd "$(dirname "$0")"

MODE="${1:-all}"

case "$MODE" in
  worker)
    echo "Starting Celery worker..."
    celery -A jobs.celery_app worker \
      --loglevel=info \
      --concurrency=2
    ;;
  beat)
    echo "Starting Celery beat scheduler..."
    celery -A jobs.celery_app beat \
      --loglevel=info
    ;;
  flower)
    echo "Starting Flower monitor at http://localhost:5555 ..."
    celery -A jobs.celery_app flower \
      --port=5555
    ;;
  all)
    echo "Starting Celery worker + beat..."
    echo "  Worker: 2 processes"
    echo "  Beat: swap/15s, transfer/30s, price/60s, health/60s"
    echo ""
    celery -A jobs.celery_app worker \
      --beat \
      --loglevel=info \
      --concurrency=2
    ;;
  *)
    echo "Usage: $0 [worker|beat|flower|all]"
    exit 1
    ;;
esac
