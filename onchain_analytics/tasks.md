# ACU Token Analytics - Implementation Plan

## Overview
Analytics platform for ACU token on BSC (Binance Smart Chain). Collects swap/transfer data from PancakeSwap V3 pool, analyzes trading patterns, and visualizes via dashboard.

---

## Phase 1: Foundation & Infrastructure — DONE

- [x] Python project structure with config, requirements.txt
- [x] Next.js dashboard project (App Router + Tailwind + SWR)
- [x] Docker Compose (TimescaleDB + Redis)
- [x] `.env` + `.env.example` with all config vars
- [x] `config.py` with Pydantic Settings
- [x] Database schema (`db/init.sql`) with hypertables, indexes, views
- [x] SQLAlchemy models (`db/models.py`) — Swap, Price, Holder, Transfer, SyncState
- [x] Async session management (`db/database.py`)

## Phase 2: Data Collection — DONE

- [x] BSC connection manager with 5 RPC fallbacks + rate limiter
- [x] Pool swaps collector (PancakeSwap V3 Swap events → prices)
- [x] Token transfers collector (ERC-20 Transfer events → holder balances)
- [x] Price aggregator (raw swaps → OHLCV candles, multiple intervals)
- [x] Incremental sync via SyncState (last_block tracking)
- [x] `run_collectors.py` — CLI with --once / --continuous / --health modes
- [x] Standalone test script (`test_standalone.py`) — live BSC data without DB

## Phase 3: Analysis — DONE

- [x] Trading metrics (volume, buy/sell ratio, trade size stats, hourly patterns)
- [x] Whale analysis (detection, concentration, accumulation vs distribution)
- [x] Wallet P&L (FIFO-based realized/unrealized, ROI, holder distribution)

## Phase 4: API — DONE

- [x] FastAPI app with lifespan, CORS, error handling
- [x] Pydantic schemas (20+ response models)
- [x] Price router (current, stats, history, 24h)
- [x] Swaps router (recent, latest, large trades)
- [x] Holders router (list, top, by address, distribution, count)
- [x] Whales router (list, summary, concentration, activity, accumulating/distributing)
- [x] Analytics router (overview, volume, buy-sell, trade-size, hourly, wallet P&L)
- [x] Health check endpoint

## Phase 5: Dashboard — DONE

- [x] Overview page (price, volume, activity stats, recent swaps, live feed)
- [x] Trades page (swap history with filtering)
- [x] Holders page (top holders, distribution)
- [x] Whales page (concentration, activity, sentiment)
- [x] Reusable components (StatCard, PriceChart, SwapTable, HolderTable, Navigation)
- [x] Type-safe API client (`lib/api.ts`)

---

## Phase 6: Make It Run — DONE

### 6.1: Infrastructure (no Docker — using Homebrew PostgreSQL 15 + Redis)
- [x] PostgreSQL 15 running via Homebrew, `acu_analytics` DB with all 5 tables
- [x] Redis running via Homebrew
- [x] Python async DB connection verified

### 6.2: Collectors
- [x] Health check passes (BSC connected, block number, chain_id=56)
- [x] Single sync pass completes (swaps, transfers, price aggregation)
- [x] Data in DB: 20 swaps, 54 price candles, 5 holders
- [x] **Fix:** `bsc_connection` now uses `RPC_RATE_LIMIT` from settings
- [x] **Fix:** Price aggregator — replaced TimescaleDB `time_bucket()` with standard PostgreSQL `date_trunc()` + floor
- [x] **Fix:** Added missing unique index on `prices(timestamp, interval)` for upserts
- [x] **Fix:** Increased BATCH_SIZE from 10 → 2000

### 6.3: API
- [x] FastAPI starts, all endpoints return data
- [x] Tested: `/health`, `/price`, `/swaps`, `/holders/top`, `/price/history`, `/analytics/overview`
- [x] **Fix:** `regex` → `pattern` deprecation in price router

### 6.4: Dashboard
- [x] Next.js serves at localhost:3000, pages render with API data
- [x] Created `.env.local` with API URL config

### 6.5: End-to-end
- [x] Full pipeline works: collectors → DB → API → dashboard

---

## Phase 7: Testing & Reliability — DONE

### 7.1: Test infrastructure
- [x] `pytest.ini` with asyncio auto mode
- [x] `tests/conftest.py` — transactional DB sessions (auto-rollback), sample_swaps (10), sample_holders (5), seeded_db fixture
- [x] Isolation: fixture data uses block_number=99000000+ and address prefix "0xtest" to avoid conflicts with real DB data

### 7.2: Collector tests (17 tests) — `tests/test_collectors.py`
- [x] Price calculation: sqrtPriceX96 → USDT conversion, edge cases
- [x] Swap event parsing: buy/sell detection, address extraction, timestamp
- [x] Transfer event parsing: amount decimals, address lowercasing
- [x] Timestamp truncation: all 6 intervals (1m, 5m, 15m, 1h, 4h, 1d)

### 7.3: Analysis tests (13 tests) — `tests/test_analysis.py`
- [x] Trading metrics: volume, buy/sell counts, price range, trade size, net flow
- [x] Holder analysis: count, top holder, descending order, concentration, labels
- [x] Whale detection: threshold filtering, positive balances, trade counts

### 7.4: API endpoint tests (17 tests) — `tests/test_api.py`
- [x] Root & health endpoints
- [x] Price endpoints (current, history, invalid interval, 24h stats)
- [x] Swaps endpoints (list, limit, invalid hours)
- [x] Holders endpoints (top, count, distribution)
- [x] Analytics endpoints (overview, volume, buy-sell)
- [x] Whales endpoints (summary, concentration)

### 7.5: Bugs found and fixed during testing
- [x] **Fix:** `func.cast(Swap.is_buy, type_=Decimal)` → `type_=Integer` in `acu_price.py` (Decimal is not a SQLAlchemy type)
- [x] **Fix:** Removed dead buggy query in `whales.py` (SELECT SUM with ORDER BY + LIMIT without GROUP BY)

### Result: 47/47 tests pass

## Phase 8: Job Scheduling — DONE

### 8.1: Celery App Setup
- [x] Create `jobs/celery_app.py` — Celery instance with Redis broker (db/1) + result backend (db/2)
- [x] Configure: JSON serialization, `task_acks_late`, soft/hard time limits (120s/180s), 2 worker processes
- [x] Add `jobs/__init__.py` with task autodiscovery

### 8.2: Celery Tasks
- [x] Create `jobs/tasks.py` — wrap existing async collectors as Celery tasks
- [x] `sync_swaps_task` — calls `sync_swaps()` via `asyncio.run()`, autoretry 3x with exponential backoff
- [x] `sync_transfers_task` — calls `sync_transfers()` via `asyncio.run()`, autoretry 3x
- [x] `aggregate_prices_task` — calls `aggregate_all_intervals()` (last hour), autoretry 3x
- [x] `health_check_task` — calls `bsc_connection.health_check()`, logs status, max 1 retry
- [x] Each task returns a result dict (for monitoring)
- [x] `task_postrun` signal stores last result per task in Redis (`acu:task_last:*` keys)

### 8.3: Celery Beat Schedule
- [x] Configure periodic schedule in `celery_app.py`:
  - Swap sync: every 15 seconds
  - Transfer sync: every 30 seconds
  - Price aggregation: every 60 seconds
  - Health check: every 60 seconds
- [x] Create `run_worker.sh` helper script (worker / beat / flower / all modes)

### 8.4: Error Handling & Monitoring
- [x] Task retry with exponential backoff (max 3 retries, capped at 60s)
- [x] Failure logging with context (task name, exception, traceback via exc_info)
- [x] Add `/jobs/status` API endpoint — reads `acu:task_last:*` from Redis, shows per-task status
- [x] Add Flower to requirements for optional web-based monitoring (`./run_worker.sh flower`)

### Result: 47/47 tests still pass, Celery app + tasks import OK

## Phase 9: Polish — DONE

### 9.1: Structured Logging
- [x] Create `utils/logging.py` — centralized structlog config (JSON in prod, colored console in dev)
- [x] Add `LOG_LEVEL` and `LOG_FORMAT` settings to `config.py`
- [x] Replace `logging.basicConfig` in `run_collectors.py` with structlog setup
- [x] Update all 7 Python modules to use `get_logger()` from structlog
- [x] Add request logging middleware to FastAPI (method, path, status, duration_ms)

### 9.2: Alembic Migrations
- [x] Run `alembic init alembic` to scaffold migration directory
- [x] Configure `alembic/env.py` to use sync engine + existing models (Base.metadata)
- [x] Set `alembic.ini` sqlalchemy.url dynamically from `config.py`
- [x] Generate initial baseline migration (empty — schema already exists from init.sql)
- [x] Stamp DB at head (`alembic stamp head`) — verified with `alembic current`

### 9.3: WebSocket for Live Data
- [x] Create `api/routers/ws.py` — WebSocket endpoint at `/ws/live`
- [x] Broadcast latest price + recent swaps on new data (3s poll loop)
- [x] ConnectionManager pattern — tracks clients, auto-cleans dead connections
- [x] Add WebSocket route to `api/main.py`
- [x] Price alert trigger: notify when price change > 5% in 5 min window

### 9.4: Dashboard Real-time Updates
- [x] Add `dashboard/lib/websocket.ts` — WebSocket client hook with auto-reconnect
- [x] Update PriceDisplay to prefer WS price, fallback to SWR polling
- [x] SwapFeed uses WS swaps when connected, falls back to polling
- [x] Add "Live" / "Connecting..." / "Offline" indicator in Navigation (colored dot)
- [x] Add `AlertToast` component — whale/price alert toast notifications (auto-dismiss 8s)
- [x] Add `LiveProviders` wrapper in root layout for global alert rendering

### Result: 47/47 Python tests pass, TypeScript compiles clean

---

## Review Section

### Phase 8 Review
- **Changes made:**
  - `jobs/celery_app.py` — Celery app config with Redis broker, beat schedule
  - `jobs/tasks.py` — 4 tasks wrapping async collectors + postrun signal for monitoring
  - `api/routers/jobs.py` — `/jobs/status` endpoint reading task results from Redis
  - `api/main.py` — registered jobs router
  - `run_worker.sh` — convenience script for starting worker/beat/flower
  - `requirements.txt` — added flower
- **Challenges encountered:** Async-to-sync bridge needed for Celery (solved with `asyncio.run()`)
- **Deviations from plan:** Beat intervals are longer than `run_collectors.py` (15s vs 3s for swaps) — Celery task dispatch overhead makes sub-10s impractical, but this is fine for production
- **Lessons learned:** Celery `task_acks_late=True` is critical for reliability — prevents losing tasks if a worker crashes mid-execution

### Phase 9 Review
- **Changes made:**
  - `utils/logging.py` + `utils/__init__.py` — centralized structlog config (console/JSON modes)
  - `config.py` — added `log_level`, `log_format` settings
  - 7 Python files — replaced `import logging` with `from utils.logging import get_logger`
  - `api/main.py` — request logging middleware (method, path, status, duration)
  - `alembic/` directory — scaffolded, `env.py` wired to models, baseline migration, DB stamped
  - `alembic.ini` — dynamic URL from config
  - `api/routers/ws.py` — WebSocket `/ws/live` endpoint with ConnectionManager, price alerts
  - `dashboard/lib/websocket.ts` — React hook with auto-reconnect, exponential backoff
  - `dashboard/components/PriceDisplay.tsx` — hybrid WS+polling price
  - `dashboard/components/SwapTable.tsx` — SwapFeed prefers WS when connected
  - `dashboard/components/Navigation.tsx` — live connection indicator (green/yellow/red dot)
  - `dashboard/components/AlertToast.tsx` — price alert toast notifications
  - `dashboard/components/LiveProviders.tsx` — global client wrapper in layout
  - `dashboard/app/globals.css` — slide-in animation for toasts
  - `dashboard/app/layout.tsx` — added LiveProviders
- **Challenges encountered:**
  - structlog `add_logger_name` incompatible with PrintLoggerFactory → switched to stdlib LoggerFactory
  - Alembic autogenerate detected index name diffs (init.sql used `idx_*`, SQLAlchemy uses `ix_*`) → replaced with empty baseline migration + stamp
- **Deviations from plan:** None — all 4 sub-phases completed as planned
- **Lessons learned:** structlog works best when routed through stdlib LoggerFactory so third-party libraries (uvicorn, celery) output in the same format
