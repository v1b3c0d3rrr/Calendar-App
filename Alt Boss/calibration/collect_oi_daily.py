#!/usr/bin/env python3
"""
Phase 5.3: Daily OI collection to SQLite.

Collects current OI for all Binance USDT-M perpetual futures and appends
to a growing SQLite database. Designed to run via cron:

    0 8 * * * cd /Users/a1111/Antigravity_Intro/Alt\ Boss && calibration/venv/bin/python calibration/collect_oi_daily.py

Table schema:
    oi_daily(symbol TEXT, date TEXT, oi_contracts REAL, oi_value_usd REAL,
             PRIMARY KEY(symbol, date))
"""

import os
import sys
import time
import json
import sqlite3
import requests
from datetime import datetime, timezone

# ---------- Config ----------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOTS_DIR = os.path.join(SCRIPT_DIR, "oi_snapshots")
os.makedirs(SNAPSHOTS_DIR, exist_ok=True)

DB_PATH = os.path.join(SNAPSHOTS_DIR, "oi_history.db")
BINANCE_FAPI = "https://fapi.binance.com"
REQUEST_DELAY = 0.2

TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# ---------- Rate-limited requests ----------

last_call = 0.0


def binance_get(endpoint: str, params: dict = None) -> dict:
    """Rate-limited GET to Binance Futures API."""
    global last_call
    elapsed = time.time() - last_call
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)
    url = f"{BINANCE_FAPI}{endpoint}"
    last_call = time.time()
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


# ---------- Database ----------

def init_db(conn: sqlite3.Connection):
    """Create table if not exists."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS oi_daily (
            symbol TEXT NOT NULL,
            date TEXT NOT NULL,
            oi_contracts REAL,
            oi_value_usd REAL,
            PRIMARY KEY (symbol, date)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_oi_daily_date ON oi_daily(date)
    """)
    conn.commit()


# ---------- Collection ----------

def get_futures_symbols() -> list[str]:
    """Get all USDT-M perpetual futures symbols."""
    data = binance_get("/fapi/v1/exchangeInfo")
    symbols = []
    for s in data["symbols"]:
        if (s["quoteAsset"] == "USDT"
                and s["contractType"] == "PERPETUAL"
                and s["status"] == "TRADING"):
            symbols.append(s["symbol"])
    symbols.sort()
    return symbols


def collect_current_oi(symbols: list[str]) -> list[tuple]:
    """
    Fetch current OI for each symbol using /fapi/v1/openInterest.
    Returns list of (symbol, date, oi_contracts, oi_value_usd) tuples.

    Note: /fapi/v1/openInterest returns current snapshot (not historical),
    so we also fetch the latest ticker price to compute USD value.
    """
    # First, get all ticker prices in one call (no rate limit needed)
    print("  Fetching ticker prices...")
    prices_resp = requests.get(f"{BINANCE_FAPI}/fapi/v1/ticker/price", timeout=30)
    prices_resp.raise_for_status()
    price_map = {p["symbol"]: float(p["price"]) for p in prices_resp.json()}

    rows = []
    errors = []
    total = len(symbols)

    for i, sym in enumerate(symbols):
        if (i + 1) % 100 == 0 or i == 0:
            print(f"  Collecting OI: {i+1}/{total}...")

        try:
            data = binance_get("/fapi/v1/openInterest", params={"symbol": sym})
            oi_contracts = float(data["openInterest"])
            price = price_map.get(sym, 0)
            oi_value_usd = oi_contracts * price
            rows.append((sym, TODAY, oi_contracts, oi_value_usd))
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            errors.append(f"{sym}: HTTP {status}")
        except Exception as e:
            errors.append(f"{sym}: {e}")

    print(f"  Collected OI for {len(rows)}/{total} symbols")
    if errors:
        print(f"  Errors ({len(errors)}): {errors[:5]}{'...' if len(errors) > 5 else ''}")
    return rows


def insert_rows(conn: sqlite3.Connection, rows: list[tuple]) -> int:
    """Insert or replace OI rows into database. Returns count of rows inserted."""
    conn.executemany(
        "INSERT OR REPLACE INTO oi_daily (symbol, date, oi_contracts, oi_value_usd) VALUES (?, ?, ?, ?)",
        rows
    )
    conn.commit()
    return len(rows)


# ---------- Main ----------

def main():
    print(f"=== Daily OI Collection — {TODAY} ===")

    # Check if already collected today
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    existing = conn.execute(
        "SELECT COUNT(*) FROM oi_daily WHERE date = ?", (TODAY,)
    ).fetchone()[0]

    if existing > 0:
        print(f"  Already have {existing} rows for {TODAY}. Replacing...")

    # Collect
    symbols = get_futures_symbols()
    print(f"  {len(symbols)} USDT-M perpetual symbols found")

    rows = collect_current_oi(symbols)

    # Insert
    count = insert_rows(conn, rows)
    print(f"  Inserted {count} rows into {DB_PATH}")

    # Stats
    total_dates = conn.execute("SELECT COUNT(DISTINCT date) FROM oi_daily").fetchone()[0]
    total_rows = conn.execute("SELECT COUNT(*) FROM oi_daily").fetchone()[0]
    print(f"  Database: {total_rows} total rows across {total_dates} date(s)")

    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
