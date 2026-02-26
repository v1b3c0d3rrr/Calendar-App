"""
FastAPI dependencies for database sessions, rate limiting, etc.
"""
from typing import Annotated, AsyncGenerator

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import async_session_maker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield database session for request."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


# Type alias for dependency injection
DbSession = Annotated[AsyncSession, Depends(get_db)]


# Common query parameters
def pagination_params(
    limit: int = Query(default=50, ge=1, le=500, description="Max items to return"),
    offset: int = Query(default=0, ge=0, description="Items to skip"),
) -> dict:
    return {"limit": limit, "offset": offset}


def time_range_params(
    hours: int = Query(default=24, ge=1, le=720, description="Time range in hours"),
) -> dict:
    return {"hours": hours}


PaginationDep = Annotated[dict, Depends(pagination_params)]
TimeRangeDep = Annotated[dict, Depends(time_range_params)]
