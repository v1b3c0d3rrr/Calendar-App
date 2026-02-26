// API Response Types

export interface PriceResponse {
  price: number;
  timestamp: string;
  tx_hash?: string;
}

export interface PriceStats {
  period_hours: number;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  change: number | null;
  change_pct: number | null;
}

export interface OHLCVCandle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume_usdt: number;
  volume_acu: number;
  trade_count: number;
}

export interface Swap {
  tx_hash: string;
  timestamp: string;
  block_number: number;
  type: 'buy' | 'sell';
  amount_acu: number;
  amount_usdt: number;
  price_usdt: number;
  sender: string;
  recipient: string;
}

export interface Holder {
  address: string;
  balance: number;
  percentage?: number;
  trade_count: number;
  first_seen: string;
  last_active: string;
  label?: string;
  is_contract?: boolean;
}

export interface MarketOverview {
  timestamp: string;
  price: {
    current: number | null;
    change_24h: number | null;
    change_24h_pct: number | null;
    high_24h: number | null;
    low_24h: number | null;
  };
  volume: {
    volume_24h_usdt: number;
    volume_24h_acu: number;
    volume_7d_usdt: number;
    trades_24h: number;
    trades_7d: number;
  };
  trading: {
    buy_count_24h: number;
    sell_count_24h: number;
    buy_sell_ratio: number | null;
    net_flow_usdt: number;
    avg_trade_usdt: number;
    median_trade_usdt: number;
  };
  holders: {
    total_holders: number;
    unique_traders_24h: number;
  };
}

export interface Whale {
  address: string;
  balance: number;
  percentage_of_supply: number;
  trade_count: number;
  first_seen: string;
  last_active: string;
  label?: string;
}

export interface WhaleConcentration {
  total_supply: number;
  top_10: { total_balance: number; percentage: number };
  top_50: { total_balance: number; percentage: number };
  whales: { threshold: number; count: number; total_balance: number; percentage: number };
}

export interface WhaleSummary {
  timestamp: string;
  concentration: WhaleConcentration;
  top_whales: Whale[];
  activity_24h: {
    total_trades: number;
    buys: number;
    sells: number;
    sentiment: string;
  };
  large_trades_24h: Swap[];
}

export interface HourlyVolume {
  hour: string;
  volume_usdt: number;
  volume_acu: number;
  trade_count: number;
  buys: number;
  sells: number;
}
