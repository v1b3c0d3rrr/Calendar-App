"""
Daily Screener — скрининг всех Binance спот+фьючерс токенов по калиброванным порогам.
Выводит кандидатов, прошедших минимальный фильтр для дальнейшего /research.

Фильтры (из empirical_thresholds.yaml):
1. Vol/MC ratio > 0.03 (winners median 5.4%, losers 0.76%)
2. MC/FDV ratio < 0.30 (winners median 0.156, losers 0.738)
3. Price 7d > 0% (winners +6.4%, losers -9%)
4. Supply ratio < 0.50 (winners 0.37, losers 0.98)
5. Volume 24h > $100K (liquidity gate)

Scoring: buy_combo (min 2 of 3 core rules) → candidates for /research
"""

import os
import sys
import time
import json
import requests
from datetime import datetime, timezone

# Load .env
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

CG_API_KEY = os.getenv("CG_API_KEY", "")
CG_BASE = "https://api.coingecko.com/api/v3"
CG_HEADERS = {"x-cg-demo-api-key": CG_API_KEY} if CG_API_KEY else {}

# Rate limiter
last_cg_call = 0.0

def cg_get(endpoint, params=None):
    global last_cg_call
    elapsed = time.time() - last_cg_call
    if elapsed < 0.3:
        time.sleep(0.3 - elapsed)
    url = f"{CG_BASE}{endpoint}"
    last_cg_call = time.time()
    resp = requests.get(url, headers=CG_HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ── Binance API ──────────────────────────────────────────────

def get_binance_spot_symbols():
    """Все USDT spot base assets."""
    r = requests.get("https://api.binance.com/api/v3/exchangeInfo", timeout=30)
    r.raise_for_status()
    symbols = set()
    for s in r.json()["symbols"]:
        if (s["quoteAsset"] == "USDT"
            and s["status"] == "TRADING"
            and s.get("isSpotTradingAllowed", True)):
            symbols.add(s["baseAsset"])
    return symbols


def get_binance_futures_symbols():
    """Все USDT-M perpetual base assets."""
    r = requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo", timeout=30)
    r.raise_for_status()
    symbols = set()
    for s in r.json()["symbols"]:
        if (s["quoteAsset"] == "USDT"
            and s["contractType"] == "PERPETUAL"
            and s["status"] == "TRADING"):
            # Strip 1000 prefix for matching
            base = s["baseAsset"]
            if base.startswith("1000"):
                base = base[4:]
            symbols.add(base)
    return symbols


# ── CoinGecko Symbol Resolution ─────────────────────────────

# Known overrides for ambiguous symbols
SYMBOL_OVERRIDES = {
    "BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin",
    "SOL": "solana", "XRP": "ripple", "DOGE": "dogecoin",
    "ADA": "cardano", "AVAX": "avalanche-2", "DOT": "polkadot",
    "LINK": "chainlink", "SHIB": "shiba-inu", "UNI": "uniswap",
    "LTC": "litecoin", "ATOM": "cosmos", "FIL": "filecoin",
    "APT": "aptos", "ARB": "arbitrum", "OP": "optimism",
    "SUI": "sui", "SEI": "sei-network", "TIA": "celestia",
    "INJ": "injective-protocol", "FET": "fetch-ai",
    "RENDER": "render-token", "RNDR": "render-token",
    "NEAR": "near", "ICP": "internet-computer", "STX": "blockstack",
    "IMX": "immutable-x", "PEPE": "pepe", "WIF": "dogwifcoin",
    "FLOKI": "floki", "BONK": "bonk", "WLD": "worldcoin-wld",
    "STRK": "starknet", "MANTA": "manta-network",
    "JUP": "jupiter-exchange-solana", "PYTH": "pyth-network",
    "JTO": "jito-governance-token", "TRX": "tron",
    "ALGO": "algorand", "FTM": "fantom", "SAND": "the-sandbox",
    "MANA": "decentraland", "AXS": "axie-infinity", "GALA": "gala",
    "ENS": "ethereum-name-service", "LDO": "lido-dao",
    "RPL": "rocket-pool", "SSV": "ssv-network", "AAVE": "aave",
    "MKR": "maker", "CRV": "curve-dao-token",
    "COMP": "compound-governance-token", "SNX": "havven",
    "SUSHI": "sushi", "CAKE": "pancakeswap-token",
    "1INCH": "1inch", "DYDX": "dydx-chain", "GMX": "gmx",
    "PENDLE": "pendle", "ENA": "ethena", "EIGEN": "eigenlayer",
    "W": "wormhole", "ZRO": "layerzero", "ONDO": "ondo-finance",
    "TON": "the-open-network", "HBAR": "hedera-hashgraph",
    "XLM": "stellar", "VET": "vechain", "THETA": "theta-token",
    "RUNE": "thorchain", "GRT": "the-graph", "FLR": "flare-networks",
    "MASK": "mask-network", "ONE": "harmony",
    "ROSE": "oasis-network", "KAVA": "kava", "ZIL": "zilliqa",
    "CELO": "celo", "FLOW": "flow", "MINA": "mina-protocol",
    "CHZ": "chiliz", "BAT": "basic-attention-token",
    "IOTA": "iota", "EOS": "eos", "XTZ": "tezos",
    "NEO": "neo", "ZEC": "zcash", "DASH": "dash",
    "WAVES": "waves", "QTUM": "qtum", "ICX": "icon",
    "ONT": "ontology", "ZEN": "zencash", "SC": "siacoin",
    "STORJ": "storj", "SKL": "skale", "COTI": "coti",
    "CELR": "celer-network", "DENT": "dent",
    "HOT": "holotoken", "ANKR": "ankr", "BAND": "band-protocol",
    "RLC": "iexec-rlc", "NKN": "nkn", "OGN": "origin-protocol",
    "AUDIO": "audius", "LINA": "linear", "REEF": "reef",
    "SXP": "swipe", "ALPHA": "alpha-venture-dao",
    "TLM": "alien-worlds", "PEOPLE": "constitutiondao",
    "LEVER": "lever", "LOOM": "loom-network-new",
    "BICO": "biconomy", "API3": "api3", "ACH": "alchemy-pay",
    "T": "threshold-network-token", "EDU": "edu-coin",
    "MAGIC": "magic", "RDNT": "radiant-capital",
    "WOO": "woo-network", "BLUR": "blur",
    "ID": "space-id", "CYBER": "cyber-connect",
    "ARKM": "arkham", "NTRN": "neutron-3",
    "ORDI": "ordinals", "BOME": "book-of-meme",
    "ETHFI": "ether-fi", "DYM": "dymension",
    "PIXEL": "pixels", "PORTAL": "portal-2",
    "AEVO": "aevo", "ACE": "fusionist",
    "AI": "sleepless-ai", "XAI": "xai-blockchain",
    "ALT": "altlayer", "MEME": "memecoin-2",
    "NFP": "nonfungible-friend",
    "S": "sonic-3", "G": "gravity-bridge-g",
    "ME": "magic-eden",
    "TRUMP": "official-trump", "MELANIA": "melania-meme",
    "TST": "the-standard-token", "LAYER": "unilayer",
    "KAITO": "kaito", "SHELL": "myshell",
    "FORM": "binaryx", "NIL": "nil-2",
    "PARTI": "particle-network",
    "SIGN": "sign-2",
    "INIT": "initia",
    "PNUT": "peanut-the-squirrel",
    "THE": "thena",
    "MOVE": "movement",
    "VANA": "vana",
    "BIO": "bio-protocol",
    "USUAL": "usual",
    "COOKIE": "cookie",
    "ANIME": "animecoin",
    "BERA": "berachain",
    "IP": "story-protocol",
    "BMT": "bmtoken",
    "BABY": "baby",
    "GPS": "gps",
    "RED": "red-2",
    "KMNO": "kamino",
    "BANANAS31": "bananas31",
    "SIREN": "siren",
    "HAEDAL": "haedal",
    "SKYAI": "skyai-2",
    "BROCCOLI714": "broccoli714",
    "TUT": "tutorial",
    "MYX": "myx-finance",
    "GUN": "gunz-2",
    "ARC": "ai-rig-complex",
}


def build_cg_symbol_map():
    """Build symbol -> CG id map from /coins/list."""
    coins = cg_get("/coins/list")
    sym_map = {}
    for c in coins:
        sym = c["symbol"].upper()
        if sym not in sym_map:
            sym_map[sym] = []
        sym_map[sym].append({"id": c["id"], "name": c["name"]})
    return sym_map


def resolve_cg_ids(symbols, cg_sym_map):
    """Resolve Binance symbols to CoinGecko IDs."""
    resolved = {}
    unresolved = []
    for sym in sorted(symbols):
        if sym in SYMBOL_OVERRIDES:
            resolved[sym] = SYMBOL_OVERRIDES[sym]
        elif sym in cg_sym_map:
            candidates = cg_sym_map[sym]
            # Pick first candidate (heuristic)
            resolved[sym] = candidates[0]["id"]
        else:
            unresolved.append(sym)
    return resolved, unresolved


# ── CoinGecko Market Data ───────────────────────────────────

def fetch_market_data(cg_ids):
    """Fetch full market data for CG ids in batches of 250."""
    all_data = {}
    id_list = list(set(cg_ids.values()))

    for i in range(0, len(id_list), 250):
        batch = id_list[i:i+250]
        try:
            data = cg_get("/coins/markets", params={
                "vs_currency": "usd",
                "ids": ",".join(batch),
                "per_page": 250,
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "7d"
            })
            for coin in data:
                all_data[coin["id"]] = coin
            print(f"  Batch {i//250+1}: {len(data)} coins")
        except Exception as e:
            print(f"  Batch {i//250+1} error: {e}")
        time.sleep(0.5)

    return all_data


# ── Screening Logic ─────────────────────────────────────────

def screen_token(sym, cg_id, market):
    """Apply calibrated thresholds. Returns (score, signals, data) or None."""
    mc = market.get("market_cap") or 0
    fdv = market.get("fully_diluted_valuation") or 0
    vol = market.get("total_volume") or 0
    price = market.get("current_price") or 0
    circ = market.get("circulating_supply") or 0
    total = market.get("total_supply") or 0
    price_7d = market.get("price_change_percentage_7d_in_currency") or market.get("price_change_percentage_24h") or 0
    ath = market.get("ath") or 0

    # Skip stablecoins and wrapped tokens
    name_lower = (market.get("name") or "").lower()
    sym_lower = sym.lower()
    if any(x in name_lower for x in ["usd", "tether", "dai ", "busd", "wrapped", "bridged"]):
        return None
    if any(x in sym_lower for x in ["usd", "busd", "dai", "tusd", "fdusd"]):
        return None

    # Skip if no meaningful market cap
    if mc < 1_000_000:  # < $1M = probably wrong CG ID
        return None

    # Skip large cap (>$2B) — not our target for 2x
    if mc > 2_000_000_000:
        return None

    # Liquidity gate
    if vol < 100_000:
        return None

    # Calculate metrics
    vol_mc = vol / mc if mc > 0 else 0
    mc_fdv = mc / fdv if fdv > 0 else 1.0
    supply_ratio = circ / total if total > 0 else 1.0
    ath_dd = ((price - ath) / ath * 100) if ath > 0 else 0

    # ── Buy Combo (from empirical_thresholds.yaml) ──
    # At least 2 of 3 core rules
    signals = []
    combo_score = 0

    # Rule 1: Vol/MC > 3%
    if vol_mc > 0.10:
        signals.append(f"vol_mc={vol_mc:.1%} [STRONG]")
        combo_score += 2
    elif vol_mc > 0.03:
        signals.append(f"vol_mc={vol_mc:.1%} [BUY]")
        combo_score += 1

    # Rule 2: MC/FDV < 0.30 (scarcity)
    if mc_fdv < 0.10:
        signals.append(f"mc_fdv={mc_fdv:.2f} [EXTREME SCARCITY]")
        combo_score += 2
    elif mc_fdv < 0.30:
        signals.append(f"mc_fdv={mc_fdv:.2f} [SCARCITY]")
        combo_score += 1

    # Rule 3: Price 7d > 0% (momentum)
    if price_7d > 5:
        signals.append(f"price_7d={price_7d:+.1f}% [MOMENTUM]")
        combo_score += 2
    elif price_7d > 0:
        signals.append(f"price_7d={price_7d:+.1f}% [POSITIVE]")
        combo_score += 1

    # Bonus: Supply ratio < 0.40
    if supply_ratio < 0.40:
        signals.append(f"supply={supply_ratio:.0%} [SCARCE]")
        combo_score += 1

    # Need combo_score >= 2 (at least 2 rules triggered)
    if combo_score < 2:
        return None

    # Cap tier
    if mc < 50_000_000:
        cap_tier = "micro"
    elif mc < 300_000_000:
        cap_tier = "small"
    elif mc < 2_000_000_000:
        cap_tier = "mid"
    else:
        cap_tier = "large"

    # Cluster hint based on ATH drawdown
    if ath_dd < -70:
        cluster_hint = "A_deep_recovery"
    elif -70 <= ath_dd < -40:
        cluster_hint = "E_v_reversal or B_gradual"
    elif -40 <= ath_dd < -30:
        cluster_hint = "C_breakout"
    else:
        cluster_hint = "D_momentum or C_breakout"

    return {
        "symbol": sym,
        "name": market.get("name", ""),
        "cg_id": cg_id,
        "price": price,
        "market_cap": mc,
        "fdv": fdv,
        "volume_24h": vol,
        "vol_mc": vol_mc,
        "mc_fdv": mc_fdv,
        "supply_ratio": supply_ratio,
        "price_7d_pct": price_7d,
        "price_24h_pct": market.get("price_change_percentage_24h") or 0,
        "ath_drawdown_pct": ath_dd,
        "cap_tier": cap_tier,
        "cluster_hint": cluster_hint,
        "combo_score": combo_score,
        "signals": signals,
    }


# ── Main ────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print(f"  DAILY SCREENER — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 70)

    # Step 1: Get Binance tokens on both spot + futures
    print("\n[1/4] Fetching Binance exchange info...")
    spot = get_binance_spot_symbols()
    futures = get_binance_futures_symbols()
    both = spot & futures
    print(f"  Spot: {len(spot)} | Futures: {len(futures)} | Both: {len(both)}")

    # Step 2: Resolve CoinGecko IDs
    print("\n[2/4] Resolving CoinGecko IDs...")
    cg_sym_map = build_cg_symbol_map()
    cg_ids, unresolved = resolve_cg_ids(both, cg_sym_map)
    print(f"  Resolved: {len(cg_ids)} | Unresolved: {len(unresolved)}")
    if unresolved:
        print(f"  Unresolved: {unresolved}")

    # Step 3: Fetch market data
    print("\n[3/4] Fetching market data from CoinGecko...")
    market_data = fetch_market_data(cg_ids)
    print(f"  Got data for {len(market_data)} tokens")

    # Step 4: Screen
    print("\n[4/4] Applying calibrated filters...")
    candidates = []
    for sym, cg_id in cg_ids.items():
        if cg_id not in market_data:
            continue
        result = screen_token(sym, cg_id, market_data[cg_id])
        if result:
            candidates.append(result)

    # Sort by combo_score desc, then vol_mc desc
    candidates.sort(key=lambda x: (-x["combo_score"], -x["vol_mc"]))

    # Print results
    def fmt(n):
        if n >= 1e9: return f"${n/1e9:.2f}B"
        if n >= 1e6: return f"${n/1e6:.1f}M"
        if n >= 1e3: return f"${n/1e3:.0f}K"
        return f"${n:.0f}"

    print(f"\n{'='*70}")
    print(f"  CANDIDATES: {len(candidates)} tokens passed screening")
    print(f"{'='*70}\n")

    for i, c in enumerate(candidates, 1):
        print(f"{'─'*60}")
        print(f"  #{i} {c['symbol']} ({c['name']}) — combo_score: {c['combo_score']}")
        print(f"  Price: ${c['price']:.6g}  |  MC: {fmt(c['market_cap'])}  |  FDV: {fmt(c['fdv'])}  |  Vol24h: {fmt(c['volume_24h'])}")
        print(f"  Vol/MC: {c['vol_mc']:.1%}  |  MC/FDV: {c['mc_fdv']:.2f}  |  Supply: {c['supply_ratio']:.0%}")
        print(f"  Price 24h: {c['price_24h_pct']:+.1f}%  |  Price 7d: {c['price_7d_pct']:+.1f}%  |  ATH dd: {c['ath_drawdown_pct']:.0f}%")
        print(f"  Cap tier: {c['cap_tier']}  |  Cluster hint: {c['cluster_hint']}")
        print(f"  Signals: {' | '.join(c['signals'])}")

    # Save results
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "screened": len(cg_ids),
        "candidates_count": len(candidates),
        "candidates": candidates,
    }

    outdir = os.path.dirname(os.path.abspath(__file__))
    outpath = os.path.join(outdir, f"screen_{datetime.now().strftime('%Y%m%d')}.json")
    with open(outpath, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n✓ Results saved to {outpath}")

    # Print summary for research
    if candidates:
        print(f"\n{'='*70}")
        print(f"  RESEARCH QUEUE (top candidates by combo_score):")
        print(f"{'='*70}")
        for c in candidates:
            print(f"  → {c['symbol']:10s} combo={c['combo_score']}  vol_mc={c['vol_mc']:.1%}  mc_fdv={c['mc_fdv']:.2f}  7d={c['price_7d_pct']:+.1f}%  MC={fmt(c['market_cap'])}")

    return candidates


if __name__ == "__main__":
    candidates = main()
