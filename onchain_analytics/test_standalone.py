#!/usr/bin/env python3
"""
Standalone ACU Token Analytics Test
Works without database - fetches live data from BSC.
"""
import time
from datetime import datetime, timezone
from decimal import Decimal
from web3 import Web3
from eth_abi import decode

# ===========================================
# Configuration
# ===========================================

RPC_ENDPOINTS = [
    'https://bsc-dataseed.binance.org',
    'https://bsc-dataseed1.binance.org',
]

ACU_ADDRESS = '0x6ef2ffb38d64afe18ce782da280b300e358cfeaf'
USDT_ADDRESS = '0x55d398326f99059ff775485246999027b3197955'
POOL_ADDRESS = '0xbfEbc33B770a6261A945051087dB281fda8b8513'

ACU_DECIMALS = 12
USDT_DECIMALS = 18

# Event topics
SWAP_TOPIC = '0x19b47279256b2a23a1665c810c8d55a1758940ee09377d4f8d26497a3577dc83'
TRANSFER_TOPIC = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

# ===========================================
# Helpers
# ===========================================

def get_web3():
    """Connect to BSC."""
    for endpoint in RPC_ENDPOINTS:
        try:
            w3 = Web3(Web3.HTTPProvider(endpoint, request_kwargs={'timeout': 30}))
            if w3.is_connected():
                return w3
        except:
            continue
    raise Exception("Could not connect to BSC")


def format_number(num, decimals=2):
    """Format large numbers."""
    if abs(num) >= 1_000_000:
        return f"{num/1_000_000:,.{decimals}f}M"
    if abs(num) >= 1_000:
        return f"{num/1_000:,.{decimals}f}K"
    return f"{num:,.{decimals}f}"


def format_address(addr):
    """Shorten address."""
    return f"{addr[:6]}...{addr[-4:]}"


def calculate_price(sqrt_price_x96):
    """Calculate ACU price in USDT from sqrtPriceX96."""
    Q96 = 2**96
    price_ratio = (Decimal(sqrt_price_x96) / Decimal(Q96)) ** 2
    decimal_adjustment = Decimal(10 ** (USDT_DECIMALS - ACU_DECIMALS))
    acu_per_usdt = price_ratio * decimal_adjustment
    return Decimal(1) / acu_per_usdt if acu_per_usdt > 0 else Decimal(0)


# ===========================================
# Data Fetchers
# ===========================================

def get_token_info(w3):
    """Get ACU token information."""
    ERC20_ABI = [
        {'constant': True, 'inputs': [], 'name': 'name', 'outputs': [{'name': '', 'type': 'string'}], 'type': 'function'},
        {'constant': True, 'inputs': [], 'name': 'symbol', 'outputs': [{'name': '', 'type': 'string'}], 'type': 'function'},
        {'constant': True, 'inputs': [], 'name': 'decimals', 'outputs': [{'name': '', 'type': 'uint8'}], 'type': 'function'},
        {'constant': True, 'inputs': [], 'name': 'totalSupply', 'outputs': [{'name': '', 'type': 'uint256'}], 'type': 'function'},
    ]

    contract = w3.eth.contract(address=Web3.to_checksum_address(ACU_ADDRESS), abi=ERC20_ABI)

    return {
        'name': contract.functions.name().call(),
        'symbol': contract.functions.symbol().call(),
        'decimals': contract.functions.decimals().call(),
        'total_supply': contract.functions.totalSupply().call() / 10**ACU_DECIMALS,
    }


def get_pool_state(w3):
    """Get current pool state and price."""
    POOL_ABI = [
        {'inputs': [], 'name': 'liquidity', 'outputs': [{'name': '', 'type': 'uint128'}], 'stateMutability': 'view', 'type': 'function'},
        {'inputs': [], 'name': 'slot0', 'outputs': [
            {'name': 'sqrtPriceX96', 'type': 'uint160'},
            {'name': 'tick', 'type': 'int24'},
            {'name': 'observationIndex', 'type': 'uint16'},
            {'name': 'observationCardinality', 'type': 'uint16'},
            {'name': 'observationCardinalityNext', 'type': 'uint16'},
            {'name': 'feeProtocol', 'type': 'uint32'},
            {'name': 'unlocked', 'type': 'bool'}
        ], 'stateMutability': 'view', 'type': 'function'},
    ]

    pool = w3.eth.contract(address=Web3.to_checksum_address(POOL_ADDRESS), abi=POOL_ABI)

    liquidity = pool.functions.liquidity().call()
    slot0 = pool.functions.slot0().call()

    sqrt_price_x96 = slot0[0]
    tick = slot0[1]
    price = calculate_price(sqrt_price_x96)

    return {
        'liquidity': liquidity,
        'sqrt_price_x96': sqrt_price_x96,
        'tick': tick,
        'price_usdt': float(price),
    }


def get_recent_swaps(w3, block_range=50):
    """Fetch recent swap events."""
    current_block = w3.eth.block_number

    try:
        logs = w3.eth.get_logs({
            'address': Web3.to_checksum_address(POOL_ADDRESS),
            'fromBlock': current_block - block_range,
            'toBlock': current_block,
            'topics': [SWAP_TOPIC]
        })
    except Exception as e:
        print(f"  (Rate limited, trying smaller range...)")
        try:
            logs = w3.eth.get_logs({
                'address': Web3.to_checksum_address(POOL_ADDRESS),
                'fromBlock': current_block - 10,
                'toBlock': current_block,
                'topics': [SWAP_TOPIC]
            })
        except:
            return []

    swaps = []
    for log in logs:
        try:
            # Decode swap data
            data = bytes(log['data'])
            amount0, amount1, sqrt_price_x96, liquidity, tick = decode(
                ['int256', 'int256', 'uint160', 'uint128', 'int24'],
                data
            )

            # token0=USDT, token1=ACU
            amount_usdt = abs(amount0) / 10**USDT_DECIMALS
            amount_acu = abs(amount1) / 10**ACU_DECIMALS
            price = calculate_price(sqrt_price_x96)

            # Determine buy/sell (positive amount1 = buying ACU)
            is_buy = amount1 > 0

            sender = '0x' + log['topics'][1].hex()[-40:]
            recipient = '0x' + log['topics'][2].hex()[-40:]

            swaps.append({
                'block': log['blockNumber'],
                'tx_hash': log['transactionHash'].hex(),
                'type': 'BUY' if is_buy else 'SELL',
                'amount_acu': amount_acu,
                'amount_usdt': amount_usdt,
                'price': float(price),
                'sender': sender,
                'recipient': recipient,
            })
        except Exception as e:
            continue

    return swaps


def get_recent_transfers(w3, block_range=30):
    """Fetch recent ACU transfers."""
    current_block = w3.eth.block_number

    try:
        logs = w3.eth.get_logs({
            'address': Web3.to_checksum_address(ACU_ADDRESS),
            'fromBlock': current_block - block_range,
            'toBlock': current_block,
            'topics': [TRANSFER_TOPIC]
        })
    except:
        return []

    transfers = []
    for log in logs:
        try:
            from_addr = '0x' + log['topics'][1].hex()[-40:]
            to_addr = '0x' + log['topics'][2].hex()[-40:]
            value = int(log['data'].hex(), 16) / 10**ACU_DECIMALS

            transfers.append({
                'block': log['blockNumber'],
                'from': from_addr,
                'to': to_addr,
                'amount': value,
            })
        except:
            continue

    return transfers


# ===========================================
# Main Display
# ===========================================

def print_header(title):
    """Print section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def main():
    """Run standalone analytics test."""
    print("\n" + "="*60)
    print("        ACU TOKEN ANALYTICS - STANDALONE TEST")
    print("="*60)

    # Connect
    print("\n[1] Connecting to BSC...")
    w3 = get_web3()
    current_block = w3.eth.block_number
    print(f"    Connected! Block: {current_block:,}")

    # Token Info
    print_header("TOKEN INFO")
    token_info = get_token_info(w3)
    print(f"  Name:         {token_info['name']}")
    print(f"  Symbol:       {token_info['symbol']}")
    print(f"  Decimals:     {token_info['decimals']}")
    print(f"  Total Supply: {format_number(token_info['total_supply'], 0)} ACU")

    # Pool State & Price
    print_header("CURRENT PRICE")
    pool = get_pool_state(w3)
    print(f"  ACU Price:    ${pool['price_usdt']:.6f}")
    print(f"  Tick:         {pool['tick']}")
    print(f"  Liquidity:    {pool['liquidity']:,}")

    # Market Cap
    mcap = token_info['total_supply'] * pool['price_usdt']
    print(f"  Market Cap:   ${format_number(mcap)}")

    # Recent Swaps
    print_header("RECENT SWAPS (last 50 blocks)")
    swaps = get_recent_swaps(w3, 50)

    if swaps:
        print(f"  Found {len(swaps)} swaps\n")
        print(f"  {'Type':<6} {'Amount ACU':>14} {'Amount USDT':>14} {'Price':>12}")
        print(f"  {'-'*6} {'-'*14} {'-'*14} {'-'*12}")

        for swap in swaps[-10:]:  # Show last 10
            type_color = '\033[92m' if swap['type'] == 'BUY' else '\033[91m'
            reset = '\033[0m'
            print(f"  {type_color}{swap['type']:<6}{reset} {swap['amount_acu']:>14,.2f} {swap['amount_usdt']:>14,.2f} ${swap['price']:>10.6f}")

        # Stats
        buys = [s for s in swaps if s['type'] == 'BUY']
        sells = [s for s in swaps if s['type'] == 'SELL']
        total_volume = sum(s['amount_usdt'] for s in swaps)

        print(f"\n  Summary:")
        print(f"    Buys:   {len(buys)} trades")
        print(f"    Sells:  {len(sells)} trades")
        print(f"    Volume: ${format_number(total_volume)} USDT")
    else:
        print("  No swaps found in recent blocks")

    # Recent Transfers
    print_header("RECENT TRANSFERS (last 30 blocks)")
    transfers = get_recent_transfers(w3, 30)

    if transfers:
        print(f"  Found {len(transfers)} transfers\n")
        for t in transfers[-5:]:
            print(f"  {format_address(t['from'])} -> {format_address(t['to'])}: {format_number(t['amount'])} ACU")
    else:
        print("  No transfers found (or rate limited)")

    # Summary
    print_header("SUMMARY")
    print(f"""
  Token:        {token_info['symbol']}
  Address:      {ACU_ADDRESS}
  Pool:         {POOL_ADDRESS}

  Price:        ${pool['price_usdt']:.6f}
  Supply:       {format_number(token_info['total_supply'], 0)} ACU
  Market Cap:   ${format_number(mcap)}

  Chain:        BSC (Binance Smart Chain)
  DEX:          PancakeSwap V3
""")

    print("="*60)
    print("  Test complete!")
    print("="*60 + "\n")


def live_monitor(interval=5):
    """Live price monitor - refreshes every N seconds."""
    import sys

    print("\n" + "="*60)
    print("        ACU LIVE PRICE MONITOR")
    print("="*60)
    print("  Press Ctrl+C to stop\n")

    w3 = get_web3()
    token_info = get_token_info(w3)
    last_price = None

    try:
        while True:
            pool = get_pool_state(w3)
            price = pool['price_usdt']
            block = w3.eth.block_number
            mcap = token_info['total_supply'] * price
            timestamp = datetime.now().strftime('%H:%M:%S')

            # Price change indicator
            if last_price:
                if price > last_price:
                    indicator = '\033[92m▲\033[0m'  # Green up
                elif price < last_price:
                    indicator = '\033[91m▼\033[0m'  # Red down
                else:
                    indicator = ' '
            else:
                indicator = ' '

            # Clear line and print
            sys.stdout.write(f"\r  [{timestamp}] Block {block:,} | ACU: ${price:.6f} {indicator} | MCap: ${format_number(mcap)}    ")
            sys.stdout.flush()

            last_price = price
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\n  Monitor stopped.")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--live':
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        live_monitor(interval)
    else:
        main()
        print("  Tip: Run with --live for live price monitor")
        print("       python test_standalone.py --live [interval_seconds]\n")
