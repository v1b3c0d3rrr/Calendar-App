"""
WebSocket endpoint for real-time price and swap updates.

Clients connect to /ws/live and receive JSON messages:
  {"type": "price",  "data": {"price": 0.0045, "timestamp": "...", "change_pct": 2.1}}
  {"type": "swap",   "data": {"tx_hash": "...", "type": "buy", ...}}
  {"type": "alert",  "data": {"kind": "price_move", "change_pct": -5.2, ...}}

The server polls the DB every few seconds and pushes new data to all
connected clients. This is simpler than event-driven pub/sub and
works well for our scale.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""
    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def to_json(data: dict) -> str:
    return json.dumps(data, cls=DecimalEncoder)


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info("ws_connect", clients=len(self.active))

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)
        logger.info("ws_disconnect", clients=len(self.active))

    async def broadcast(self, message: str):
        """Send message to all connected clients, drop dead connections."""
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)


manager = ConnectionManager()

# Track last known state for change detection
_last_price: float | None = None
_last_swap_id: int | None = None
_price_5min_ago: float | None = None
_price_5min_timestamp: datetime | None = None


async def _fetch_latest_price() -> dict | None:
    """Get the most recent price from DB."""
    from collectors.prices.acu_price import get_current_price
    try:
        result = await get_current_price()
        if result:
            return {
                "price": float(result["price"]),
                "timestamp": result["timestamp"].isoformat() if hasattr(result["timestamp"], "isoformat") else str(result["timestamp"]),
            }
    except Exception as e:
        logger.debug("ws_price_fetch_error", error=str(e))
    return None


async def _fetch_latest_swaps(after_id: int | None, limit: int = 5) -> list[dict]:
    """Get recent swaps newer than after_id."""
    from sqlalchemy import select
    from db.database import get_db_session
    from db.models import Swap

    try:
        async with get_db_session() as session:
            query = select(Swap).order_by(Swap.id.desc()).limit(limit)
            if after_id:
                query = query.where(Swap.id > after_id)
            result = await session.execute(query)
            swaps = result.scalars().all()
            return [
                {
                    "id": s.id,
                    "tx_hash": s.tx_hash,
                    "timestamp": s.timestamp.isoformat(),
                    "type": "buy" if s.is_buy else "sell",
                    "amount_acu": float(s.amount_acu),
                    "amount_usdt": float(s.amount_usdt),
                    "price_usdt": float(s.price_usdt),
                    "sender": s.sender,
                }
                for s in reversed(swaps)  # chronological order
            ]
    except Exception as e:
        logger.debug("ws_swap_fetch_error", error=str(e))
        return []


async def _broadcast_loop():
    """Background loop that polls DB and broadcasts updates."""
    global _last_price, _last_swap_id, _price_5min_ago, _price_5min_timestamp

    while True:
        if not manager.active:
            await asyncio.sleep(2)
            continue

        # --- Price update ---
        price_data = await _fetch_latest_price()
        if price_data and price_data["price"] != _last_price:
            # Calculate change from 5 minutes ago
            now = datetime.now(timezone.utc)
            if _price_5min_ago is None or (
                _price_5min_timestamp and (now - _price_5min_timestamp).seconds >= 300
            ):
                _price_5min_ago = _last_price or price_data["price"]
                _price_5min_timestamp = now

            change_pct = 0.0
            if _price_5min_ago and _price_5min_ago > 0:
                change_pct = round(
                    (price_data["price"] - _price_5min_ago) / _price_5min_ago * 100, 2
                )

            price_data["change_pct"] = change_pct
            _last_price = price_data["price"]
            await manager.broadcast(to_json({"type": "price", "data": price_data}))

            # Price alert: > 5% move in 5 min window
            if abs(change_pct) >= 5.0:
                alert = {
                    "kind": "price_move",
                    "change_pct": change_pct,
                    "price": price_data["price"],
                    "timestamp": price_data["timestamp"],
                }
                await manager.broadcast(to_json({"type": "alert", "data": alert}))
                logger.warning("price_alert", change_pct=change_pct, price=price_data["price"])

        # --- New swaps ---
        new_swaps = await _fetch_latest_swaps(_last_swap_id)
        for swap in new_swaps:
            await manager.broadcast(to_json({"type": "swap", "data": swap}))
            if _last_swap_id is None or swap["id"] > _last_swap_id:
                _last_swap_id = swap["id"]

        await asyncio.sleep(3)  # Poll interval


# Background task reference (started on first connection)
_broadcast_task: asyncio.Task | None = None


@router.websocket("/live")
async def websocket_live(ws: WebSocket):
    """
    Live data WebSocket. Sends price updates, new swaps, and alerts.
    Connect and receive — no messages expected from client.
    """
    global _broadcast_task

    await manager.connect(ws)

    # Start broadcast loop if not running
    if _broadcast_task is None or _broadcast_task.done():
        _broadcast_task = asyncio.create_task(_broadcast_loop())

    # Send current price immediately on connect
    price_data = await _fetch_latest_price()
    if price_data:
        try:
            await ws.send_text(to_json({"type": "price", "data": price_data}))
        except Exception:
            pass

    try:
        # Keep connection alive — read (and discard) any client messages
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
