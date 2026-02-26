"""
Configuration management for ACU Token Analytics
Loads settings from environment variables with sensible defaults.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    postgres_user: str = "acu_user"
    postgres_password: str = "acu_password"
    postgres_db: str = "acu_analytics"
    database_url: str = "postgresql+asyncpg://a1111@localhost:5432/acu_analytics"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # BSC RPC
    bsc_rpc_primary: str = "https://bsc-dataseed.binance.org"
    bsc_rpc_fallback_1: str = "https://bsc-dataseed1.binance.org"
    bsc_rpc_fallback_2: str = "https://bsc-dataseed2.binance.org"
    bsc_rpc_fallback_3: str = "https://bsc-dataseed3.binance.org"
    bsc_rpc_fallback_4: str = "https://bsc-dataseed4.binance.org"

    # BscScan API
    bscscan_api_key: str = ""

    # Token addresses
    acu_token_address: str = "0x6ef2ffb38d64afe18ce782da280b300e358cfeaf"
    usdt_token_address: str = "0x55d398326f99059ff775485246999027b3197955"
    pool_address: str = "0xbfEbc33B770a6261A945051087dB281fda8b8513"

    # Token decimals
    acu_decimals: int = 12
    usdt_decimals: int = 18

    # Collector settings
    start_block: int = 0
    batch_size: int = 1000
    rpc_rate_limit: int = 10

    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # Logging
    log_level: str = "INFO"
    log_format: str = "console"  # "console" for dev (colored), "json" for production

    @property
    def bsc_rpc_endpoints(self) -> list[str]:
        """List of RPC endpoints for fallback."""
        return [
            self.bsc_rpc_primary,
            self.bsc_rpc_fallback_1,
            self.bsc_rpc_fallback_2,
            self.bsc_rpc_fallback_3,
            self.bsc_rpc_fallback_4,
        ]

    @property
    def sync_database_url(self) -> str:
        """Synchronous database URL for Alembic and scripts."""
        return self.database_url.replace("+asyncpg", "")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience export
settings = get_settings()
