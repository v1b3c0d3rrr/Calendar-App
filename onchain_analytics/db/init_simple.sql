-- ===========================================
-- ACU Token Analytics - Simple Database Init
-- (Without TimescaleDB for MVP)
-- ===========================================

-- Swaps table
CREATE TABLE IF NOT EXISTS swaps (
    id BIGSERIAL PRIMARY KEY,
    tx_hash VARCHAR(66) NOT NULL,
    block_number BIGINT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    log_index INTEGER NOT NULL,
    sender VARCHAR(42) NOT NULL,
    recipient VARCHAR(42) NOT NULL,
    amount_acu NUMERIC(38, 18) NOT NULL,
    amount_usdt NUMERIC(38, 18) NOT NULL,
    price_usdt NUMERIC(38, 18) NOT NULL,
    is_buy BOOLEAN NOT NULL,
    sqrt_price_x96 VARCHAR(80),
    liquidity VARCHAR(80),
    tick INTEGER
);

-- Prices table (OHLCV candles)
CREATE TABLE IF NOT EXISTS prices (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    interval VARCHAR(10) NOT NULL,
    open NUMERIC(38, 18) NOT NULL,
    high NUMERIC(38, 18) NOT NULL,
    low NUMERIC(38, 18) NOT NULL,
    close NUMERIC(38, 18) NOT NULL,
    volume_usdt NUMERIC(38, 18) NOT NULL,
    volume_acu NUMERIC(38, 18) NOT NULL,
    trade_count INTEGER NOT NULL DEFAULT 0
);

-- Holders table
CREATE TABLE IF NOT EXISTS holders (
    id BIGSERIAL PRIMARY KEY,
    address VARCHAR(42) NOT NULL UNIQUE,
    balance NUMERIC(38, 18) NOT NULL DEFAULT 0,
    first_seen TIMESTAMPTZ NOT NULL,
    last_active TIMESTAMPTZ NOT NULL,
    total_bought NUMERIC(38, 18) NOT NULL DEFAULT 0,
    total_sold NUMERIC(38, 18) NOT NULL DEFAULT 0,
    trade_count INTEGER NOT NULL DEFAULT 0,
    avg_buy_price NUMERIC(38, 18),
    is_contract BOOLEAN NOT NULL DEFAULT FALSE,
    label VARCHAR(100)
);

-- Transfers table
CREATE TABLE IF NOT EXISTS transfers (
    id BIGSERIAL PRIMARY KEY,
    tx_hash VARCHAR(66) NOT NULL,
    block_number BIGINT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    log_index INTEGER NOT NULL,
    from_address VARCHAR(42) NOT NULL,
    to_address VARCHAR(42) NOT NULL,
    amount NUMERIC(38, 18) NOT NULL
);

-- Sync state table
CREATE TABLE IF NOT EXISTS sync_state (
    id SERIAL PRIMARY KEY,
    collector_name VARCHAR(50) NOT NULL UNIQUE,
    last_block BIGINT NOT NULL DEFAULT 0,
    last_timestamp TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    extra_state TEXT
);

-- ===========================================
-- Indexes
-- ===========================================

-- Swaps indexes
CREATE INDEX IF NOT EXISTS idx_swaps_timestamp ON swaps (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_swaps_tx_hash ON swaps (tx_hash);
CREATE INDEX IF NOT EXISTS idx_swaps_block_number ON swaps (block_number);
CREATE INDEX IF NOT EXISTS idx_swaps_sender ON swaps (sender);
CREATE INDEX IF NOT EXISTS idx_swaps_recipient ON swaps (recipient);
CREATE UNIQUE INDEX IF NOT EXISTS idx_swaps_block_log ON swaps (block_number, log_index);

-- Prices indexes
CREATE INDEX IF NOT EXISTS idx_prices_interval_timestamp ON prices (interval, timestamp DESC);

-- Holders indexes
CREATE INDEX IF NOT EXISTS idx_holders_balance ON holders (balance DESC);
CREATE INDEX IF NOT EXISTS idx_holders_last_active ON holders (last_active DESC);

-- Transfers indexes
CREATE INDEX IF NOT EXISTS idx_transfers_timestamp ON transfers (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_transfers_tx_hash ON transfers (tx_hash);
CREATE INDEX IF NOT EXISTS idx_transfers_from ON transfers (from_address);
CREATE INDEX IF NOT EXISTS idx_transfers_to ON transfers (to_address);
CREATE INDEX IF NOT EXISTS idx_transfers_block_number ON transfers (block_number);
CREATE UNIQUE INDEX IF NOT EXISTS idx_transfers_block_log ON transfers (block_number, log_index);

-- ===========================================
-- Initial sync state records
-- ===========================================

INSERT INTO sync_state (collector_name, last_block) VALUES
    ('pool_swaps', 0),
    ('token_transfers', 0)
ON CONFLICT (collector_name) DO NOTHING;

-- ===========================================
-- Useful views
-- ===========================================

-- Current price (latest swap)
CREATE OR REPLACE VIEW v_current_price AS
SELECT
    price_usdt,
    timestamp,
    tx_hash
FROM swaps
ORDER BY timestamp DESC
LIMIT 1;

-- 24h stats
CREATE OR REPLACE VIEW v_24h_stats AS
SELECT
    COUNT(*) as trade_count,
    SUM(ABS(amount_usdt)) as volume_usdt,
    SUM(ABS(amount_acu)) as volume_acu,
    COUNT(DISTINCT sender) as unique_traders,
    SUM(CASE WHEN is_buy THEN 1 ELSE 0 END) as buys,
    SUM(CASE WHEN NOT is_buy THEN 1 ELSE 0 END) as sells
FROM swaps
WHERE timestamp > NOW() - INTERVAL '24 hours';

-- Top holders
CREATE OR REPLACE VIEW v_top_holders AS
SELECT
    address,
    balance,
    trade_count,
    last_active,
    label
FROM holders
WHERE balance > 0
ORDER BY balance DESC
LIMIT 100;
