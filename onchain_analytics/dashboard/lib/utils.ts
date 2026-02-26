import { clsx, type ClassValue } from 'clsx';

// Classname helper
export function cn(...inputs: ClassValue[]) {
  return clsx(inputs);
}

// Number formatting
export function formatNumber(num: number, decimals = 2): string {
  if (num === null || num === undefined) return '-';

  if (Math.abs(num) >= 1_000_000) {
    return (num / 1_000_000).toFixed(decimals) + 'M';
  }
  if (Math.abs(num) >= 1_000) {
    return (num / 1_000).toFixed(decimals) + 'K';
  }
  return num.toFixed(decimals);
}

export function formatCurrency(num: number, decimals = 2): string {
  if (num === null || num === undefined) return '-';
  return '$' + formatNumber(num, decimals);
}

export function formatPrice(num: number): string {
  if (num === null || num === undefined) return '-';

  if (num < 0.0001) {
    return '$' + num.toExponential(4);
  }
  if (num < 1) {
    return '$' + num.toFixed(6);
  }
  return '$' + num.toFixed(4);
}

export function formatPercent(num: number | null | undefined): string {
  if (num === null || num === undefined) return '-';
  const sign = num >= 0 ? '+' : '';
  return sign + num.toFixed(2) + '%';
}

// Address formatting
export function shortenAddress(address: string, chars = 4): string {
  if (!address) return '';
  return `${address.slice(0, chars + 2)}...${address.slice(-chars)}`;
}

// Time formatting
export function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function formatDate(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatRelativeTime(timestamp: string): string {
  const now = new Date();
  const date = new Date(timestamp);
  const diff = now.getTime() - date.getTime();

  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (seconds < 60) return `${seconds}s ago`;
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  return `${days}d ago`;
}

// Color helpers
export function getPriceChangeColor(change: number | null | undefined): string {
  if (change === null || change === undefined) return 'text-gray-500';
  return change >= 0 ? 'text-buy' : 'text-sell';
}

export function getTradeTypeColor(type: 'buy' | 'sell'): string {
  return type === 'buy' ? 'text-buy' : 'text-sell';
}

export function getTradeTypeBg(type: 'buy' | 'sell'): string {
  return type === 'buy' ? 'bg-buy/10' : 'bg-sell/10';
}

// BscScan link
export function getBscScanTxUrl(txHash: string): string {
  return `https://bscscan.com/tx/${txHash}`;
}

export function getBscScanAddressUrl(address: string): string {
  return `https://bscscan.com/address/${address}`;
}
