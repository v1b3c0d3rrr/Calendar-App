'use client';

import useSWR from 'swr';
import { api } from './api';

// SWR configuration
const defaultConfig = {
  revalidateOnFocus: false,
  dedupingInterval: 2000,
};

// Price hooks
export function usePrice(refreshInterval = 5000) {
  return useSWR('price', api.getPrice, {
    ...defaultConfig,
    refreshInterval,
  });
}

export function usePriceStats(hours = 24) {
  return useSWR(`price-stats-${hours}`, () => api.getPriceStats(hours), {
    ...defaultConfig,
    refreshInterval: 30000,
  });
}

export function usePriceHistory(interval = '1h', limit = 100) {
  return useSWR(
    `price-history-${interval}-${limit}`,
    () => api.getPriceHistory(interval, limit),
    {
      ...defaultConfig,
      refreshInterval: 60000,
    }
  );
}

// Swaps hooks
export function useLatestSwaps(limit = 10, refreshInterval = 3000) {
  return useSWR(
    `latest-swaps-${limit}`,
    () => api.getLatestSwaps(limit),
    {
      ...defaultConfig,
      refreshInterval,
    }
  );
}

export function useSwaps(params?: { hours?: number; type?: string; limit?: number }) {
  const key = `swaps-${JSON.stringify(params)}`;
  return useSWR(key, () => api.getSwaps(params), {
    ...defaultConfig,
    refreshInterval: 10000,
  });
}

export function useLargeSwaps(hours = 24, minUsdt = 1000) {
  return useSWR(
    `large-swaps-${hours}-${minUsdt}`,
    () => api.getLargeSwaps(hours, minUsdt),
    {
      ...defaultConfig,
      refreshInterval: 30000,
    }
  );
}

// Holders hooks
export function useHolders(params?: { limit?: number; sort?: string }) {
  const key = `holders-${JSON.stringify(params)}`;
  return useSWR(key, () => api.getHolders(params), {
    ...defaultConfig,
    refreshInterval: 60000,
  });
}

export function useTopHolders(limit = 20) {
  return useSWR(`top-holders-${limit}`, () => api.getTopHolders(limit), {
    ...defaultConfig,
    refreshInterval: 60000,
  });
}

export function useHolderDistribution() {
  return useSWR('holder-distribution', api.getHolderDistribution, {
    ...defaultConfig,
    refreshInterval: 300000,
  });
}

// Analytics hooks
export function useMarketOverview(refreshInterval = 10000) {
  return useSWR('market-overview', api.getOverview, {
    ...defaultConfig,
    refreshInterval,
  });
}

export function useHourlyVolume(hours = 24) {
  return useSWR(`hourly-volume-${hours}`, () => api.getHourlyVolume(hours), {
    ...defaultConfig,
    refreshInterval: 60000,
  });
}

export function useWalletAnalysis(address: string) {
  return useSWR(
    address ? `wallet-${address}` : null,
    () => api.getWalletAnalysis(address),
    defaultConfig
  );
}

// Whale hooks
export function useWhaleSummary(refreshInterval = 30000) {
  return useSWR('whale-summary', api.getWhaleSummary, {
    ...defaultConfig,
    refreshInterval,
  });
}

export function useWhaleConcentration() {
  return useSWR('whale-concentration', api.getWhaleConcentration, {
    ...defaultConfig,
    refreshInterval: 300000,
  });
}

export function useWhaleActivity(hours = 24) {
  return useSWR(
    `whale-activity-${hours}`,
    () => api.getWhaleActivity(hours),
    {
      ...defaultConfig,
      refreshInterval: 30000,
    }
  );
}

export function useAccumulators(days = 7) {
  return useSWR(`accumulators-${days}`, () => api.getAccumulators(days), {
    ...defaultConfig,
    refreshInterval: 300000,
  });
}

export function useDistributors(days = 7) {
  return useSWR(`distributors-${days}`, () => api.getDistributors(days), {
    ...defaultConfig,
    refreshInterval: 300000,
  });
}
