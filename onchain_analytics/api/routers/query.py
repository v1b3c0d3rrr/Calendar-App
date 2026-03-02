"""
Natural language query endpoint.
Converts user questions to SQL via Ollama (local LLM), executes read-only,
and returns structured results with a visualization hint.
"""
import re
from datetime import datetime, date
from decimal import Decimal

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from config import settings
from db.database import async_session_maker
from utils.logging import get_logger

logger = get_logger("api.query")

router = APIRouter()

# ---------------------------------------------------------------------------
# Schema description fed to the LLM so it knows our tables
# ---------------------------------------------------------------------------
DB_SCHEMA = """
Tables in PostgreSQL database:

1. swaps (swap events from ACU/USDT pool)
   - id BIGINT PK
   - tx_hash VARCHAR(66), block_number BIGINT, timestamp TIMESTAMPTZ
   - log_index INT, sender VARCHAR(42), recipient VARCHAR(42)
   - amount_acu NUMERIC(38,18), amount_usdt NUMERIC(38,18)
   - price_usdt NUMERIC(38,18), is_buy BOOLEAN
   - sqrt_price_x96 VARCHAR(80), liquidity VARCHAR(80), tick INT

2. prices (OHLCV candles aggregated from swaps)
   - id BIGINT PK
   - timestamp TIMESTAMPTZ, interval VARCHAR(10)  -- '1m','5m','15m','1h','4h','1d'
   - open NUMERIC, high NUMERIC, low NUMERIC, close NUMERIC
   - volume_usdt NUMERIC, volume_acu NUMERIC, trade_count INT

3. holders (ACU token holders)
   - id BIGINT PK
   - address VARCHAR(42) UNIQUE, balance NUMERIC(38,18)
   - first_seen TIMESTAMPTZ, last_active TIMESTAMPTZ
   - total_bought NUMERIC, total_sold NUMERIC, trade_count INT
   - avg_buy_price NUMERIC, is_contract BOOLEAN, label VARCHAR(100)

4. transfers (ERC-20 Transfer events)
   - id BIGINT PK
   - tx_hash VARCHAR(66), block_number BIGINT, timestamp TIMESTAMPTZ
   - log_index INT, from_address VARCHAR(42), to_address VARCHAR(42)
   - amount NUMERIC(38,18)

5. sync_state (collector progress)
   - id INT PK
   - collector_name VARCHAR(50) UNIQUE, last_block BIGINT
   - last_timestamp TIMESTAMPTZ, updated_at TIMESTAMPTZ
   - extra_state TEXT
"""

SYSTEM_PROMPT = f"""You are a SQL assistant for a blockchain analytics database.
Given a user question, output ONLY a single PostgreSQL SELECT statement.

Rules:
- SELECT only. Never INSERT, UPDATE, DELETE, DROP, ALTER, or any DDL/DML.
- Always add LIMIT 100 unless the user explicitly asks for more.
- No markdown, no explanations, no code fences — just raw SQL.
- Use standard PostgreSQL functions (date_trunc, etc.). No TimescaleDB.
- For "recent" or "last N days" use: timestamp > NOW() - INTERVAL '...'
- For boolean is_buy: TRUE = buy, FALSE = sell.

{DB_SCHEMA}"""

# ---------------------------------------------------------------------------
# SQL validation
# ---------------------------------------------------------------------------
FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|EXECUTE|COPY)\b",
    re.IGNORECASE,
)


def validate_sql(sql: str) -> str:
    """Validate and clean generated SQL. Raises ValueError on bad SQL."""
    sql = sql.strip().rstrip(";")

    # Strip markdown code fences if the model slips them in
    if sql.startswith("```"):
        lines = sql.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        sql = "\n".join(lines).strip().rstrip(";")

    if not sql.upper().lstrip().startswith(("SELECT", "WITH")):
        raise ValueError("Only SELECT / WITH queries are allowed.")

    if FORBIDDEN_KEYWORDS.search(sql):
        raise ValueError("Query contains forbidden keywords.")

    if ";" in sql:
        raise ValueError("Multi-statement queries are not allowed.")

    return sql


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------
async def text_to_sql(question: str) -> str:
    """Convert a natural-language question to SQL via Ollama (local)."""
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/chat",
            json={
                "model": settings.ollama_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ],
                "stream": False,
                "options": {"temperature": 0},
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------
def _serialise(value):
    """Make a DB value JSON-safe."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


async def execute_query(sql: str) -> dict:
    """Validate, run read-only SQL, and return structured results."""
    sql = validate_sql(sql)

    async with async_session_maker() as session:
        result = await session.execute(text(sql))
        columns = list(result.keys())
        rows = [[_serialise(v) for v in row] for row in result.fetchall()]

    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
    }


# ---------------------------------------------------------------------------
# Visualization hint
# ---------------------------------------------------------------------------
def detect_visualization(columns: list[str], rows: list, sql: str) -> str:
    """Suggest a chart type based on data shape."""
    sql_upper = sql.upper()
    col_count = len(columns)
    row_count = len(rows)

    # Single value → table
    if row_count <= 1 and col_count <= 2:
        return "table"

    # Time column + numeric → line chart
    time_words = {"timestamp", "date", "time", "day", "hour", "month", "week"}
    has_time = any(c.lower() in time_words or "time" in c.lower() or "date" in c.lower() for c in columns)
    if has_time and col_count >= 2:
        return "line_chart"

    # GROUP BY with counts/sums and few rows → bar chart
    if ("GROUP BY" in sql_upper or "COUNT" in sql_upper) and row_count <= 20:
        return "bar_chart"

    # Two columns, small set, one numeric → pie chart
    if col_count == 2 and row_count <= 8:
        if rows and isinstance(rows[0][1], (int, float)):
            return "pie_chart"

    return "table"


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    question: str
    sql: str
    columns: list[str]
    rows: list[list]
    row_count: int
    visualization_hint: str


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------
@router.post("", response_model=QueryResponse)
async def ask_question(body: QueryRequest):
    """Convert a natural-language question to SQL and return results."""
    # Check Ollama is reachable
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.get(f"{settings.ollama_url}/api/tags")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Ollama is not running. Start with: brew services start ollama")

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # 1. Generate SQL
    try:
        sql = await text_to_sql(question)
    except Exception as exc:
        logger.error("llm_error", error=str(exc))
        raise HTTPException(status_code=502, detail=f"LLM error: {exc}")

    # 2. Execute
    try:
        result = await execute_query(sql)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("query_error", sql=sql, error=str(exc))
        raise HTTPException(status_code=400, detail=f"SQL execution error: {exc}")

    # 3. Suggest visualization
    hint = detect_visualization(result["columns"], result["rows"], sql)

    return QueryResponse(
        question=question,
        sql=sql,
        **result,
        visualization_hint=hint,
    )
