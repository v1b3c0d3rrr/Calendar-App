"""
Unified address label database.

Sources:
1. brianleect/etherscan-labels — scraped Etherscan/BSCScan/etc labels
2. Hardcoded CEX hot wallets (Binance, Kucoin, Bybit, Gate, OKX, MEXC)
3. Hardcoded DEX routers/factories (Uniswap, PancakeSwap, SushiSwap)
4. Heuristic labeling for unknown addresses (Phase 3)

Usage:
    from label_db import LabelDB
    db = LabelDB()
    db.load_all()
    label = db.lookup("0x...", chain_id=1)
    # => {"name": "Binance 14", "type": "cex", "entity": "binance", "source": "etherscan-labels"}
"""

import json
import os
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent / "data"
LABELS_DIR = DATA_DIR / "labels"
ETHERSCAN_LABELS_DIR = LABELS_DIR / "etherscan-labels" / "data"

# Chain ID -> etherscan-labels folder name
CHAIN_TO_SCANNER = {
    1: "etherscan",
    56: "bscscan",
    137: "polygonscan",
    42161: "arbiscan",
    10: "optimism",
    43114: "avalanche",
    250: "ftmscan",
}

# ============================================================
# Known CEX Hot Wallets
# Sources: etherscan.io, arkham.intelligence, public reports
# ============================================================
CEX_WALLETS = {
    # Binance
    "0x28c6c06298d514db089934071355e5743bf21d60": {"name": "Binance 14", "entity": "binance"},
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": {"name": "Binance 15", "entity": "binance"},
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": {"name": "Binance 16", "entity": "binance"},
    "0x56eddb7aa87536c09ccc2793473599fd21a8b17f": {"name": "Binance 17", "entity": "binance"},
    "0x9696f59e4d72e237be84ffd425dcad154bf96976": {"name": "Binance 18", "entity": "binance"},
    "0xf977814e90da44bfa03b6295a0616a897441acec": {"name": "Binance 8", "entity": "binance"},
    "0x5a52e96bacdabb82fd05763e25335261b270efcb": {"name": "Binance 12", "entity": "binance"},
    "0xbe0eb53f46cd790cd13851d5eff43d12404d33e8": {"name": "Binance 7", "entity": "binance"},
    "0x3c783c21a0383057d128bae431894a5c19f9cf06": {"name": "Binance 9", "entity": "binance"},
    "0xb38e8c17e38363af6ebdcb3dae12e0243582891d": {"name": "Binance 10", "entity": "binance"},
    "0xe2fc31f816a9b94326492132018c3aecc4a93ae1": {"name": "Binance 11", "entity": "binance"},
    "0x8894e0a0c962cb723c1ef8a1b678046eabd700f4": {"name": "Binance 20", "entity": "binance"},
    "0x47ac0fb4f2d84898e4d9e7b4dab3c24507a6d503": {"name": "Binance: Binance-Peg Tokens", "entity": "binance"},
    # BSC Binance hot wallets
    "0x8894e0a0c962cb723c1ef8a1b678046eabd700f4": {"name": "Binance Hot Wallet (BSC)", "entity": "binance"},
    "0xe2fc31f816a9b94326492132018c3aecc4a93ae1": {"name": "Binance Hot Wallet 2 (BSC)", "entity": "binance"},

    # KuCoin
    "0xd6216fc19db775df9774a6e33526131da7d19a2c": {"name": "KuCoin 1", "entity": "kucoin"},
    "0xeb2629a2734e272bcc07bda959863f316f4bd4cf": {"name": "KuCoin 2", "entity": "kucoin"},
    "0x689c56aef474df92d44a1b70850f808488f9769c": {"name": "KuCoin 3", "entity": "kucoin"},
    "0xa1d8d972560c2f8144af871db508f0b0b10a3fbf": {"name": "KuCoin 4", "entity": "kucoin"},
    "0xf3f094484ec6901ffc9681bcb808b96bafd0b8a8": {"name": "KuCoin 5", "entity": "kucoin"},
    "0x1692e170361cefd1eb7240ec13d048fd9af6d667": {"name": "KuCoin 6", "entity": "kucoin"},
    "0x738cf6903e6c4e699d1c2dd9ab8b67fcdb3121ea": {"name": "KuCoin 7", "entity": "kucoin"},

    # Bybit
    "0xf89d7b9c864f589bbf53a82105107622b35eaa40": {"name": "Bybit 1", "entity": "bybit"},
    "0x1db92e2eebc8e0c075a02bea49a2935bcd2dfcf4": {"name": "Bybit 2", "entity": "bybit"},
    "0xa7efae728d2936e78bda97dc267687568dd593f3": {"name": "Bybit 3", "entity": "bybit"},

    # Gate.io
    "0x0d0707963952f2fba59dd06f2b425ace40b492fe": {"name": "Gate.io 1", "entity": "gate"},
    "0x7793cd85c11a924478d358d49b05b37e91b5810f": {"name": "Gate.io 2", "entity": "gate"},
    "0x1c4b70a3968436b9a0a9cf5205c787eb81bb558c": {"name": "Gate.io 3", "entity": "gate"},

    # OKX
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": {"name": "OKX 1", "entity": "okx"},
    "0x236f9f97e0e62388479bf9e5ba4889e46b0273c3": {"name": "OKX 2", "entity": "okx"},
    "0xa7efae728d2936e78bda97dc267687568dd593f3": {"name": "OKX 3", "entity": "okx"},
    "0x98ec059dc3adfbdd63429227d09cb32b3a609e4b": {"name": "OKX 4", "entity": "okx"},

    # MEXC
    "0x75e89d5979e4f6fba9f97c104c2f0afb3f1dcb88": {"name": "MEXC 1", "entity": "mexc"},
    "0x0211f3cedbef3143223d3acf0e589747933e8527": {"name": "MEXC 2", "entity": "mexc"},

    # Huobi/HTX
    "0xab5c66752a9e8167967685f1450532fb96d5d24f": {"name": "Huobi 1", "entity": "huobi"},
    "0x6748f50f686bfbca6fe8ad62b22228b87f31ff2b": {"name": "Huobi 2", "entity": "huobi"},
    "0xfdb16996831753d5331ff813c29a93c76834a0ad": {"name": "Huobi 3", "entity": "huobi"},
    "0xeee28d484628d41a82d01a21dc9649d09db6d5f9": {"name": "Huobi 4", "entity": "huobi"},
    "0x5c985e89dde482efe97ea9f1950ad149eb73829b": {"name": "Huobi 5", "entity": "huobi"},

    # Crypto.com
    "0x6262998ced04146fa42253a5c0af90ca02dfd2a3": {"name": "Crypto.com 1", "entity": "cryptocom"},
    "0x46340b20830761efd32832a74d7169b29feb9758": {"name": "Crypto.com 2", "entity": "cryptocom"},

    # Coinbase
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": {"name": "Coinbase 1", "entity": "coinbase"},
    "0x503828976d22510aad0201ac7ec88293211d23da": {"name": "Coinbase 2", "entity": "coinbase"},
    "0xddfabcdc4d8ffc6d5beaf154f18b778f892a0740": {"name": "Coinbase 3", "entity": "coinbase"},
    "0x3cd751e6b0078be393132286c442345e68ff0aef": {"name": "Coinbase 4", "entity": "coinbase"},
    "0xb5d85cbf7cb3ee0d56b3bb207d5fc4b82f43f511": {"name": "Coinbase 5", "entity": "coinbase"},

    # Bitget
    "0x97b9d2aa81f2751d4f2e26c1ba94a0dcc5e0e6c8": {"name": "Bitget 1", "entity": "bitget"},
    "0x5bdf85216ec1e38d6458c870992a69e38e03f7ef": {"name": "Bitget 2", "entity": "bitget"},
}

# ============================================================
# Known Market Maker Wallets
# Sources: Arkham Intelligence, Nansen, Etherscan labels, public reports
# ============================================================
MM_WALLETS = {
    # Wintermute (confirmed: Etherscan, Arkham, post-exploit analysis)
    "0x00000000ae347930bd1e7b0f35588b92280f9e75": {"name": "Wintermute", "entity": "wintermute"},
    "0x4f3a120e72c76c22ae802d129f599bfdbc31cb81": {"name": "Wintermute 2", "entity": "wintermute"},
    "0xdbf5e9c5206d0db70a90108bf936da60221dc080": {"name": "Wintermute 3 (Exploited)", "entity": "wintermute"},
    "0x0000000041797056e0f0fb7827ae3bdcc7b1e4e4": {"name": "Wintermute Vanity 2", "entity": "wintermute"},
    "0xb3f923eabaf178fc1bd8e13902fc5c61d3ddef5b": {"name": "Wintermute: Binance Deposit", "entity": "wintermute"},

    # DWF Labs (confirmed: Arkham, Nansen — most active on-chain MM 2024-2025)
    "0xd7cf3a1be8c93269bfdcfaf005ebb3da5e410e42": {"name": "DWF Labs", "entity": "dwf_labs"},
    "0xa7c45e581530d05a70e577e0f198458b2f1f6d78": {"name": "DWF Labs 2", "entity": "dwf_labs"},

    # Jump Trading / Jump Crypto (confirmed: Etherscan labels, Arkham)
    "0xf584f8728b874a6a5c7a8d4d387c9aae9172d621": {"name": "Jump Trading", "entity": "jump_trading"},
    "0x9507c04b10486547584c37bcbd931b2a4fee9a41": {"name": "Jump Trading 2", "entity": "jump_trading"},
    "0xcbe2cf3bd012e9c1ade2ee4d41db3dac763e4d2a": {"name": "Jump Trading 3", "entity": "jump_trading"},
    "0xf05e2a70346560d3228c7002194bb7c5dc8fe100": {"name": "Jump Trading: Binance Deposit", "entity": "jump_trading"},
    "0xe62240a57f0efbf549e278e8058f632af3ea5206": {"name": "Jump Trading: Coinbase Deposit", "entity": "jump_trading"},

    # GSR Markets (confirmed: Etherscan labels, Arkham)
    "0xca436e14855323927d6e6264470ded36455fc8bd": {"name": "GSR Markets", "entity": "gsr"},
    "0x4f3e7edf1174c06dd0e343f0be05fcbc1e42e70c": {"name": "GSR Markets 2", "entity": "gsr"},

    # Cumberland / DRW (confirmed: Arkham)
    "0x67a1cabb73c1240a1fafa62a335e1e1878e1e8cc": {"name": "Cumberland", "entity": "cumberland"},
    "0xaeb6b11c86087a3c5391e74a3e40cb54e8bd4e34": {"name": "Cumberland 2", "entity": "cumberland"},

    # Amber Group (confirmed: Etherscan labels)
    "0xe11970f2f3de9d637fb786f2d869f8fea44195ac": {"name": "Amber Group", "entity": "amber_group"},
    "0x42e5e06ef5b90fe15f853f59299fc96259209c5c": {"name": "Amber Group 2", "entity": "amber_group"},

    # Alameda Research — from etherscan-labels (27 known addresses)
    "0x073dca8acbc11ffb0b5ae7ef171e4c0b065ffa47": {"name": "Alameda Research 1", "entity": "alameda"},
    "0x712d0f306956a6a4b4f9319ad9b9de48c5345996": {"name": "Alameda Research 2", "entity": "alameda"},
    "0x93c08a3168fc469f3fc165cd3a471d19a37ca19e": {"name": "Alameda Research 3", "entity": "alameda"},
    "0x83a127952d266a6ea306c40ac62a4a70668fe3bd": {"name": "Alameda Research 5", "entity": "alameda"},
    "0x84d34f4f83a87596cd3fb6887cff8f17bf5a7b83": {"name": "Alameda Research 25", "entity": "alameda"},
    "0xfa453aec042a837e4aebbadab9d4e25b15fad69d": {"name": "Alameda Research 14", "entity": "alameda"},
    "0xf02e86d9e0efd57ad034faf52201b79917fe0713": {"name": "Alameda Research: FTT", "entity": "alameda"},

    # Auros Global (confirmed: Etherscan labels, Arkham)
    "0xff0cefdbd6bf757cc0cc361ddfbde432186ccaa6": {"name": "Auros Global", "entity": "auros"},

    # B2C2 (confirmed: Etherscan)
    "0x72a53cdbbcc1b9efa39c834a540550e23463aacb": {"name": "B2C2", "entity": "b2c2"},

    # Flowdesk (confirmed: Arkham)
    "0x1584b052702ebf74168fd0e9f6e37e1c3a03062d": {"name": "Flowdesk", "entity": "flowdesk"},
}

# ============================================================
# Known DEX Contracts
# ============================================================
DEX_CONTRACTS = {
    # === Ethereum (chain_id=1) ===
    # Uniswap V2
    "0x5c69bee701ef814a2b6a3edd4b1652cb9cc5aa6f": {"name": "Uniswap V2: Factory", "entity": "uniswap", "chain_id": 1},
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": {"name": "Uniswap V2: Router", "entity": "uniswap", "chain_id": 1},
    # Uniswap V3
    "0x1f98431c8ad98523631ae4a59f267346ea31f984": {"name": "Uniswap V3: Factory", "entity": "uniswap", "chain_id": 1},
    "0xe592427a0aece92de3edee1f18e0157c05861564": {"name": "Uniswap V3: SwapRouter", "entity": "uniswap", "chain_id": 1},
    "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": {"name": "Uniswap V3: SwapRouter02", "entity": "uniswap", "chain_id": 1},
    "0x000000000022d473030f116ddee9f6b43ac78ba3": {"name": "Uniswap: Universal Router (Permit2)", "entity": "uniswap", "chain_id": 1},
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad": {"name": "Uniswap: Universal Router", "entity": "uniswap", "chain_id": 1},
    # SushiSwap
    "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f": {"name": "SushiSwap: Router", "entity": "sushiswap", "chain_id": 1},
    "0xc0aee478e3658e2610c5f7a4a2e1777ce9e4f2ac": {"name": "SushiSwap: Factory", "entity": "sushiswap", "chain_id": 1},
    # 1inch
    "0x1111111254eeb25477b68fb85ed929f73a960582": {"name": "1inch V5: Router", "entity": "1inch", "chain_id": 1},
    "0x111111125421ca6dc452d289314280a0f8842a65": {"name": "1inch V6: Router", "entity": "1inch", "chain_id": 1},

    # === BSC (chain_id=56) ===
    # PancakeSwap V2
    "0xca143ce32fe78f1f7019d7d551a6402fc5350c73": {"name": "PancakeSwap V2: Factory", "entity": "pancakeswap", "chain_id": 56},
    "0x10ed43c718714eb63d5aa57b78b54704e256024e": {"name": "PancakeSwap V2: Router", "entity": "pancakeswap", "chain_id": 56},
    # PancakeSwap V3
    "0x0bfbcf9fa4f9c56b0f40a671ad40e0805a091865": {"name": "PancakeSwap V3: Factory", "entity": "pancakeswap", "chain_id": 56},
    "0x1b81d678ffb9c0263b24a97847620c99d213eb14": {"name": "PancakeSwap V3: SwapRouter", "entity": "pancakeswap", "chain_id": 56},
    "0x13f4ea83d0bd40e75c8222255bc855a974568dd4": {"name": "PancakeSwap V3: SmartRouter", "entity": "pancakeswap", "chain_id": 56},

    # === Arbitrum (chain_id=42161) ===
    "0x1f98431c8ad98523631ae4a59f267346ea31f984": {"name": "Uniswap V3: Factory", "entity": "uniswap", "chain_id": 42161},
    "0xe592427a0aece92de3edee1f18e0157c05861564": {"name": "Uniswap V3: SwapRouter", "entity": "uniswap", "chain_id": 42161},
    "0x1b02da8cb0d097eb8d57a175b88c7d8b47997506": {"name": "SushiSwap: Router", "entity": "sushiswap", "chain_id": 42161},
    # Camelot
    "0xc873fecbd354f5a56e00e710b90ef4201db2448d": {"name": "Camelot: Router", "entity": "camelot", "chain_id": 42161},

    # === Polygon (chain_id=137) ===
    "0x1f98431c8ad98523631ae4a59f267346ea31f984": {"name": "Uniswap V3: Factory", "entity": "uniswap", "chain_id": 137},
    "0xa5e0829caced8ffdd4de3c43696c57f7d7a678ff": {"name": "QuickSwap: Router", "entity": "quickswap", "chain_id": 137},
    "0x1b02da8cb0d097eb8d57a175b88c7d8b47997506": {"name": "SushiSwap: Router", "entity": "sushiswap", "chain_id": 137},
}

# Known Market Maker entities
MM_ENTITIES = {
    "wintermute", "dwf_labs", "dwf labs", "jump_trading", "jump trading", "jump crypto",
    "gsr", "gsr markets", "cumberland", "drw", "amber_group", "amber group",
    "alameda", "alameda research", "b2c2", "qcp_capital", "qcp capital",
    "auros", "auros global", "folkvang", "galaxy digital", "flow traders",
    "jane street", "citadel", "virtu", "tower research", "hudson river trading",
    "flowdesk", "woorton",
}

# Known DEX entities for type classification
DEX_ENTITIES = {
    "uniswap", "sushiswap", "pancakeswap", "1inch", "camelot", "quickswap",
    "balancer", "curve", "kyberswap", "dydx", "rarible", "opensea",
    "looksrare", "paraswap", "0x-protocol", "bancor", "airswap",
}
CEX_ENTITIES = {
    "binance", "kucoin", "bybit", "gate", "okx", "mexc", "huobi", "cryptocom",
    "coinbase", "bitget", "kraken", "bitfinex", "gemini", "bitstamp", "upbit",
    "bithumb", "poloniex", "htx", "bitmart", "hotbit", "hitbtc", "ftx",
    "ascendex", "remitano", "coinone", "nexo", "zb-com", "hoo-com",
    "coinmetro", "shapeshift", "crypto-com", "bitkub", "luno", "bity",
    "bitcoin-suisse",
}
# DeFi protocols that have "exchange"/"deposit" in name but are NOT CEX
DEFI_NOT_CEX = {
    # DeFi protocols with "exchange"/"deposit" in name
    "defi saver", "dutchx", "synthetix", "opyn", "hydro", "set:", "set protocol",
    "compound", "aave", "lido", "rocket pool", "olympus", "wonderland",
    "snowbank", "snowdog", "convex", "aura", "pooltogether", "mstable",
    "maker", "gitcoin", "polygon", "optimism", "arbitrum", "omg network",
    "loopring", "wyvern", "nifty gateway", "sorare", "cryptodozer",
    "excalibur", "starblock", "miime", "eristica", "minds:", "beacon deposit",
    "rubic", "gem exchange and trading", "switcheo", "mach exchange",
    "blue whale", "index protocol", "ore raid", "alkimi", "metric.exchange",
    "power index", "alameda research: wbtc", "culture exchange",
    "planetagro", "monkey billionaire", "tiger force", "ethlas",
    "panda.btm", "blockchainartexchange", "love boat", "t42 exchange",
    "boex", "coss exchange", "smoke", "next", "mandala exchange token",
    "divi exchange token", "cgcx", "idt exchange", "nash exchange",
    "excalibur exchange", "fei protocol", "index protocol",
    "sybil", "delegate", "gauntlet", "dharma",
    # Governance / delegation (NOT exchanges)
    "sybil delegate", "compound voting",
    # NFT platforms
    "nifty", "getaway open", "locked and loading",
    # Token names that contain CEX-like words
    "eristica", "cryptodozer", "cryptobuyer", "cryptodozer",
    "arca:", "power index pool",
    # DeFi with "hot wallet"
    "parex:", "panda.btm", "portto:",
    # WBTC merchants are intermediaries, not CEX
    "wbtc merchant",
    # Token contracts
    "hashtrust", "hashtrust (htx)", "sushiswap: ethtx",
    # Bancor DeFi
    "bancor: pending", "bancor network: bn",
    # Misc DeFi
    "set: defipulse", "zbtoken", "cryptocasher", "ibbt utility",
    "mco (mco)", "lunox",
}
# Labels (from etherscan scrape) that are definitely not CEX
NOT_CEX_LABELS = {
    "sybil-delegate", "delegate", "compound-governance", "nifty-gateway",
    "binance-pegged", "set-protocol", "staking", "fund", "aave",
    "entertainment", "banking", "escrow", "otc",
    "sushiswap",  # SushiSwap LP tokens with "deposit" in name
    "binance-deposit",  # label artifact, not actual CEX wallet
}


def _classify_entity(name: str, labels: list) -> str:
    """Classify an address into a type based on name and labels."""
    name_lower = name.lower()
    labels_lower = [l.lower() for l in labels]
    all_text = name_lower + " " + " ".join(labels_lower)

    # Market maker — check first (high priority)
    for mm in MM_ENTITIES:
        if mm in all_text:
            return "market_maker"

    # Step 0: Check if it's a known DeFi entity with "exchange"/"deposit" in name
    # These must NOT be classified as CEX
    is_defi_false_positive = any(fp in name_lower for fp in DEFI_NOT_CEX)

    # Step 0b: Check if any label is in the NOT_CEX_LABELS blocklist
    is_label_blocked = bool(set(labels_lower) & NOT_CEX_LABELS)

    if is_defi_false_positive or is_label_blocked:
        # Skip CEX classification entirely — will fall through to DEX/DeFi/other
        pass
    else:
        # CEX — exact entity match (high confidence)
        for cex in CEX_ENTITIES:
            if cex in all_text:
                # Guard: "binance-pegged" tokens are not CEX wallets
                if cex == "binance" and any(kw in name_lower for kw in ["pegged", "peg ", "bep-"]):
                    break
                return "cex"

        # CEX — keyword match (only if NOT a known DeFi false positive)
        # "hot wallet" — high confidence CEX signal (except known DeFi)
        if "hot wallet" in all_text:
            return "cex"
        # "deposit funder" / "deposit address" — CEX deposit pattern
        if "deposit" in all_text and any(kw in all_text for kw in ["funder", "deposit address"]):
            return "cex"

    # DEX — exact entity match
    for dex in DEX_ENTITIES:
        if dex in all_text:
            return "dex"
    if any(kw in all_text for kw in ["swap", "router", "factory", "pool", "liquidity"]):
        return "dex"
    # Catch remaining "exchange" that are DEX/DeFi
    if is_defi_false_positive and "exchange" in all_text:
        return "dex"

    # Bridge
    if any(kw in all_text for kw in ["bridge", "cross-chain", "multichain", "wormhole", "layerzero"]):
        return "bridge"

    # Staking/DeFi
    if any(kw in all_text for kw in ["staking", "vault", "lending", "aave", "compound",
                                      "depository", "depositor"]):
        return "defi"

    # Token contract
    if any(kw in all_text for kw in ["token", "erc20", "deployer"]):
        return "token"

    # MEV/Bot
    if any(kw in all_text for kw in ["mev", "bot", "flashbot", "arbitrage"]):
        return "mev_bot"

    # Airdrop
    if "airdrop" in all_text:
        return "airdrop"

    return "other"


def _extract_entity(name: str, labels: list) -> str:
    """Try to extract the entity name from label data."""
    name_lower = name.lower()
    # Check for known entities
    for entity in MM_ENTITIES | CEX_ENTITIES | DEX_ENTITIES:
        if entity in name_lower:
            return entity
    # Use first label as entity if available
    if labels:
        return labels[0].lower().replace(" ", "_")
    # Use first word of name
    if name:
        return name.split(":")[0].split(" ")[0].lower()
    return "unknown"


class LabelDB:
    """Unified address label lookup."""

    def __init__(self):
        self.labels = {}  # (chain_id, address_lower) -> label_info
        self._loaded = False

    def load_all(self):
        """Load all label sources."""
        if self._loaded:
            return

        # 1. Etherscan scraped labels
        self._load_etherscan_labels()

        # 2. Hardcoded CEX wallets
        self._load_cex_wallets()

        # 3. Hardcoded DEX contracts
        self._load_dex_contracts()

        # 4. Market maker wallets
        self._load_mm_wallets()

        self._loaded = True

    def _load_etherscan_labels(self):
        """Load brianleect/etherscan-labels JSON files."""
        for chain_id, scanner in CHAIN_TO_SCANNER.items():
            fpath = ETHERSCAN_LABELS_DIR / scanner / "combined" / "combinedAllLabels.json"
            if not fpath.exists():
                continue
            with open(fpath) as f:
                data = json.load(f)

            for addr, info in data.items():
                addr_lower = addr.lower()
                name = info.get("name", "")
                labels = info.get("labels", [])
                addr_type = _classify_entity(name, labels)
                entity = _extract_entity(name, labels)

                key = (chain_id, addr_lower)
                # Don't overwrite hardcoded CEX/DEX entries
                if key not in self.labels:
                    self.labels[key] = {
                        "name": name,
                        "type": addr_type,
                        "entity": entity,
                        "labels": labels,
                        "source": "etherscan-labels",
                    }

    def _load_cex_wallets(self):
        """Load hardcoded CEX hot wallets (apply to all chains)."""
        for addr, info in CEX_WALLETS.items():
            addr_lower = addr.lower()
            label = {
                "name": info["name"],
                "type": "cex",
                "entity": info["entity"],
                "labels": ["cex", info["entity"]],
                "source": "hardcoded",
            }
            # CEX wallets are often same address across chains
            for chain_id in [1, 56, 137, 42161, 10, 43114, 250]:
                self.labels[(chain_id, addr_lower)] = label

    def _load_dex_contracts(self):
        """Load hardcoded DEX contracts."""
        for addr, info in DEX_CONTRACTS.items():
            addr_lower = addr.lower()
            chain_id = info["chain_id"]
            self.labels[(chain_id, addr_lower)] = {
                "name": info["name"],
                "type": "dex",
                "entity": info["entity"],
                "labels": ["dex", info["entity"]],
                "source": "hardcoded",
            }

    def _load_mm_wallets(self):
        """Load hardcoded market maker wallets (apply to all chains)."""
        for addr, info in MM_WALLETS.items():
            addr_lower = addr.lower()
            label = {
                "name": info["name"],
                "type": "market_maker",
                "entity": info["entity"],
                "labels": ["market_maker", info["entity"]],
                "source": "hardcoded",
            }
            for chain_id in [1, 56, 137, 42161, 10, 43114, 250]:
                self.labels[(chain_id, addr_lower)] = label

    def lookup(self, address: str, chain_id: int = 1) -> Optional[dict]:
        """Look up an address label. Returns None if not found."""
        if not self._loaded:
            self.load_all()
        return self.labels.get((chain_id, address.lower()))

    def lookup_any_chain(self, address: str) -> Optional[dict]:
        """Look up address across all chains. Returns first match."""
        if not self._loaded:
            self.load_all()
        addr_lower = address.lower()
        for (cid, addr), label in self.labels.items():
            if addr == addr_lower:
                return {**label, "chain_id": cid}
        return None

    def stats(self) -> dict:
        """Get label database statistics."""
        if not self._loaded:
            self.load_all()

        by_chain = {}
        by_type = {}
        by_source = {}
        for (chain_id, _), info in self.labels.items():
            chain_name = {v: k for k, v in CHAIN_TO_SCANNER.items()}.get(chain_id, str(chain_id))
            by_chain[chain_id] = by_chain.get(chain_id, 0) + 1
            by_type[info["type"]] = by_type.get(info["type"], 0) + 1
            by_source[info["source"]] = by_source.get(info["source"], 0) + 1

        return {
            "total": len(self.labels),
            "by_chain": by_chain,
            "by_type": by_type,
            "by_source": by_source,
        }


def test_label_db():
    """Quick test of the label database."""
    db = LabelDB()
    db.load_all()

    stats = db.stats()
    print(f"Label DB loaded: {stats['total']} entries")
    print(f"\nBy chain: {json.dumps(stats['by_chain'], indent=2)}")
    print(f"\nBy type: {json.dumps(stats['by_type'], indent=2)}")
    print(f"\nBy source: {json.dumps(stats['by_source'], indent=2)}")

    # Test known addresses
    tests = [
        (1, "0x28c6c06298d514db089934071355e5743bf21d60", "Binance 14"),
        (56, "0x10ed43c718714eb63d5aa57b78b54704e256024e", "PancakeSwap V2: Router"),
        (1, "0x7a250d5630b4cf539739df2c5dacb4c659f2488d", "Uniswap V2: Router"),
        (1, "0xd6216fc19db775df9774a6e33526131da7d19a2c", "KuCoin 1"),
    ]
    print("\nTest lookups:")
    for chain_id, addr, expected in tests:
        result = db.lookup(addr, chain_id)
        status = "OK" if result else "MISS"
        name = result["name"] if result else "?"
        print(f"  [{status}] chain={chain_id} {expected} -> {name} (type={result['type'] if result else '?'})")


if __name__ == "__main__":
    test_label_db()
