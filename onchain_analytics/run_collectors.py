#!/usr/bin/env python3
"""
Main entry point for running ACU token data collectors.
Runs swap collector, transfer collector, and price aggregator concurrently.
"""
import asyncio
import signal
import sys
from datetime import datetime, timedelta, timezone

from collectors.bsc.connection import bsc_connection
from collectors.bsc.pool_swaps import sync_swaps
from collectors.bsc.token_transfers import sync_transfers
from collectors.prices.acu_price import aggregate_all_intervals
from utils.logging import setup_logging, get_logger

# Configure structured logging (call once at startup)
setup_logging()
logger = get_logger(__name__)

# Graceful shutdown flag
shutdown_event = asyncio.Event()


def signal_handler(sig, frame):
    """Handle shutdown signals."""
    logger.info("Shutdown signal received, stopping collectors...")
    shutdown_event.set()


async def run_swap_collector(interval: int = 3):
    """Run swap collector loop."""
    logger.info("Starting swap collector...")

    while not shutdown_event.is_set():
        try:
            result = await sync_swaps()
            if result["swaps_saved"] > 0:
                logger.info(f"Swaps: {result['swaps_saved']} new swaps saved")
        except Exception as e:
            logger.error(f"Swap collector error: {e}")

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            pass


async def run_transfer_collector(interval: int = 5):
    """Run transfer collector loop."""
    logger.info("Starting transfer collector...")

    while not shutdown_event.is_set():
        try:
            result = await sync_transfers()
            if result["transfers_saved"] > 0:
                logger.info(f"Transfers: {result['transfers_saved']} new transfers saved")
        except Exception as e:
            logger.error(f"Transfer collector error: {e}")

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            pass


async def run_price_aggregator(interval: int = 60):
    """Run price aggregation loop."""
    logger.info("Starting price aggregator...")

    while not shutdown_event.is_set():
        try:
            # Aggregate last hour of data
            start_time = datetime.now(timezone.utc) - timedelta(hours=1)
            results = await aggregate_all_intervals(start_time=start_time)
            total = sum(results.values())
            if total > 0:
                logger.info(f"Aggregated {total} price candles")
        except Exception as e:
            logger.error(f"Price aggregator error: {e}")

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            pass


async def health_check():
    """Periodic health check."""
    while not shutdown_event.is_set():
        try:
            health = await bsc_connection.health_check()
            logger.info(f"Health: {health['status']} | Block: {health.get('block_number')} | RPC: {health['endpoint']}")
        except Exception as e:
            logger.error(f"Health check error: {e}")

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=60)
            break
        except asyncio.TimeoutError:
            pass


async def run_once():
    """Run all collectors once (for testing/backfill)."""
    logger.info("Running one-time sync...")

    # Check connection
    health = await bsc_connection.health_check()
    logger.info(f"BSC Connection: {health}")

    if health["status"] != "healthy":
        logger.error("BSC connection unhealthy, aborting")
        return

    # Sync swaps
    logger.info("Syncing swaps...")
    swap_result = await sync_swaps()
    logger.info(f"Swap sync complete: {swap_result}")

    # Sync transfers
    logger.info("Syncing transfers...")
    transfer_result = await sync_transfers()
    logger.info(f"Transfer sync complete: {transfer_result}")

    # Aggregate prices
    logger.info("Aggregating prices...")
    price_result = await aggregate_all_intervals()
    logger.info(f"Price aggregation complete: {price_result}")

    logger.info("One-time sync complete!")


async def run_continuous():
    """Run all collectors continuously."""
    logger.info("Starting continuous collectors...")

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Check initial connection
    health = await bsc_connection.health_check()
    logger.info(f"BSC Connection: {health}")

    if health["status"] != "healthy":
        logger.error("BSC connection unhealthy, aborting")
        return

    # Run all collectors concurrently
    await asyncio.gather(
        run_swap_collector(interval=3),      # Every 3 seconds (BSC block time)
        run_transfer_collector(interval=5),  # Every 5 seconds
        run_price_aggregator(interval=60),   # Every minute
        health_check(),                       # Every minute
    )

    logger.info("All collectors stopped")


def main():
    """CLI entry point."""
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "--once":
            asyncio.run(run_once())
        elif command == "--continuous":
            asyncio.run(run_continuous())
        elif command == "--health":
            async def check():
                health = await bsc_connection.health_check()
                print(f"Health: {health}")
            asyncio.run(check())
        else:
            print(f"Unknown command: {command}")
            print("Usage: python run_collectors.py [--once|--continuous|--health]")
            sys.exit(1)
    else:
        print("ACU Token Data Collectors")
        print("")
        print("Usage:")
        print("  python run_collectors.py --once        Run all collectors once")
        print("  python run_collectors.py --continuous  Run collectors continuously")
        print("  python run_collectors.py --health      Check BSC connection health")


if __name__ == "__main__":
    main()
