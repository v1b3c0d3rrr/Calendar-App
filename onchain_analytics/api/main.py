"""
FastAPI application for ACU Token Analytics API.
"""
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routers import analytics, holders, jobs, price, swaps, whales, ws
from api.schemas import HealthResponse
from collectors.bsc.connection import bsc_connection
from config import settings
from utils.logging import setup_logging, get_logger

# Configure structured logging
setup_logging()
logger = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting ACU Analytics API")
    yield
    logger.info("Shutting down ACU Analytics API")


app = FastAPI(
    title="ACU Token Analytics API",
    description="Real-time analytics for ACU token on BSC",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every request with method, path, status, and duration."""
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 1)

    # Skip logging health checks and docs to reduce noise
    path = request.url.path
    if path not in ("/health", "/docs", "/openapi.json"):
        logger.info(
            "request",
            method=request.method,
            path=path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
    return response


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("unhandled_error", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.api_host == "0.0.0.0" else "An error occurred",
        },
    )


# Include routers
app.include_router(price.router, prefix="/price", tags=["Price"])
app.include_router(swaps.router, prefix="/swaps", tags=["Swaps"])
app.include_router(holders.router, prefix="/holders", tags=["Holders"])
app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
app.include_router(whales.router, prefix="/whales", tags=["Whales"])
app.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
app.include_router(ws.router, prefix="/ws", tags=["WebSocket"])


@app.get("/", tags=["Root"])
async def root():
    """API root - basic info."""
    return {
        "name": "ACU Token Analytics API",
        "version": "1.0.0",
        "token": {
            "symbol": "ACU",
            "address": settings.acu_token_address,
            "chain": "BSC",
        },
        "endpoints": {
            "price": "/price",
            "swaps": "/swaps",
            "holders": "/holders",
            "analytics": "/analytics",
            "whales": "/whales",
            "jobs": "/jobs/status",
            "ws": "ws://localhost:8000/ws/live",
            "health": "/health",
            "docs": "/docs",
        },
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """API health check endpoint."""
    # Check BSC connection
    bsc_health = await bsc_connection.health_check()

    # Check database (simple query)
    db_status = "healthy"
    try:
        from db.database import async_session_maker
        from sqlalchemy import text

        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    overall_status = "healthy" if db_status == "healthy" and bsc_health["status"] == "healthy" else "degraded"

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc).isoformat(),
        database=db_status,
        bsc_connection=bsc_health,
    )


# Run with: uvicorn api.main:app --reload
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
