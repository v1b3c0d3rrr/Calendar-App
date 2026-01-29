# Onchain Analytics Platform

Python + TypeScript stack for collecting, analyzing, and visualizing blockchain data.

## Workflow
1. First, think through the problem. Read the codebase and write a plan in tasks.md.
2. The plan should be a checklist of todo items.
3. Check in with me before starting work—I'll verify the plan.
4. Then, complete the todos one by one, marking them off as you go.
5. At every step, give me a high-level explanation of what you changed.
6. Keep every change simple and minimal. Avoid big rewrites.
7. At the end, add a review section in todo.md summarizing the changes.

## Commands
- `python -m venv venv && source venv/bin/activate` — create virtual environment
- `pip install -r requirements.txt` — install Python dependencies
- `npm install` — install JS dependencies
- `docker-compose up -d` — start DB and services
- `pytest` — run tests
- `npm run dev` — start dashboard

## Tech Stack
- **Data collection**: Python, aiohttp/httpx, web3.py
- **Database**: PostgreSQL + TimescaleDB (time series), Redis (cache)
- **Analysis**: pandas, numpy, scikit-learn
- **Dashboard**: Next.js + Tailwind + Recharts
- **Scheduling**: Celery / APScheduler

## Project Structure
```
/collectors    — data collection scripts (exchange APIs, explorers)
/db            — DB schemas, migrations, models
/analysis      — analytics and ML pipelines
/api           — FastAPI backend
/dashboard     — Next.js frontend
/jobs          — scheduled tasks
```

## Rules

### 1. API Keys Security
NEVER hardcode keys. Always use `.env` with `python-dotenv` / `process.env`.
Verify `.env` is in `.gitignore`.

### 2. Rate Limits
All API requests must go through rate limiter. Example:
```python
from ratelimit import limits, sleep_and_retry
@sleep_and_retry
@limits(calls=5, period=1)  # 5 req/sec
def fetch_data(): ...
```

### 3. API Error Handling
Always retry with exponential backoff. Log errors with context (endpoint, params).

### 4. Database Schema
Use TimescaleDB hypertables for time series. Always create indexes on:
- timestamp
- address/wallet
- token/symbol

### 5. Type Safety
Python: type hints + Pydantic for API response validation.
TypeScript: strict mode, no `any`.

### 6. Incremental Data Collection
Store `last_processed_block` / `last_timestamp`. Never re-fetch everything.

### 7. Caching
Redis for frequent queries. TTL based on data volatility:
- Prices: 10-60 sec
- Balances: 1-5 min
- Historical data: 1 hour+

### 8. ML Pipelines
Version models (MLflow/DVC). Store experiment metrics.
Feature engineering in separate modules, make it reusable.

### 9. Dashboards
Data via API, never direct DB access. SSR for SEO, CSR for real-time.
Charts: aggregate on backend, don't send raw data to frontend.

### 10. Real-time Updates
WebSocket for prices and alerts. Polling with interval for the rest.
Server-Sent Events (SSE) — simple alternative to WS.

### 11. Code Documentation
Docstrings for public functions. README in each folder explaining module purpose.

### 12. Testing
Mock external APIs (responses/pytest-httpx). Fixtures for test data.
Minimum: unit tests for parsers and transformations.

### 13. Docker
Each service in separate container. docker-compose for local development.
Production: configs via environment variables.

### 14. Git Workflow
Feature branch per task. Atomic commits with clear messages.
Before PR: tests pass, linter clean.

### 15. Explain Your Decisions
I'm learning — comment complex logic, suggest alternatives, explain trade-offs.

## Gotchas
- Binance API: different endpoints for spot and futures
- Etherscan: 5 req/sec limit on free plan
- TimescaleDB: choose chunk_time_interval based on data volume
- pandas: use chunked reading for large datasets

## When Stuck
1. Check rate limits and API keys
2. Check logs (`docker-compose logs -f`)
3. Verify DB schema and indexes
4. Ask me — I'm a beginner, explain in simple terms
