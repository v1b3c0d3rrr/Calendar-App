const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

class APIError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = 'APIError';
  }
}

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_URL}${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new APIError(
      `API Error: ${response.statusText}`,
      response.status
    );
  }

  return response.json();
}

// Price endpoints
export const api = {
  // Price
  getPrice: () => fetchAPI<{ price: number; timestamp: string }>('/price'),

  getPriceStats: (hours = 24) =>
    fetchAPI<{ period_hours: number; open: number; high: number; low: number; close: number; change: number; change_pct: number }>(
      `/price/stats?hours=${hours}`
    ),

  getPriceHistory: (interval = '1h', limit = 100) =>
    fetchAPI<{ interval: string; candles: any[]; count: number }>(
      `/price/history?interval=${interval}&limit=${limit}`
    ),

  get24hSummary: () => fetchAPI<any>('/price/24h'),

  // Swaps
  getSwaps: (params?: { hours?: number; type?: string; limit?: number }) => {
    const query = new URLSearchParams();
    if (params?.hours) query.set('hours', params.hours.toString());
    if (params?.type) query.set('type', params.type);
    if (params?.limit) query.set('limit', params.limit.toString());
    return fetchAPI<{ swaps: any[]; count: number; total: number }>(
      `/swaps?${query.toString()}`
    );
  },

  getLatestSwaps: (limit = 10) =>
    fetchAPI<any[]>(`/swaps/latest?limit=${limit}`),

  getLargeSwaps: (hours = 24, minUsdt = 1000) =>
    fetchAPI<any[]>(`/swaps/large?hours=${hours}&min_usdt=${minUsdt}`),

  // Holders
  getHolders: (params?: { limit?: number; sort?: string }) => {
    const query = new URLSearchParams();
    if (params?.limit) query.set('limit', params.limit.toString());
    if (params?.sort) query.set('sort', params.sort);
    return fetchAPI<{ holders: any[]; count: number; total_holders: number }>(
      `/holders?${query.toString()}`
    );
  },

  getTopHolders: (limit = 20) =>
    fetchAPI<any[]>(`/holders/top?limit=${limit}`),

  getHolderDistribution: () =>
    fetchAPI<{ distribution: any[] }>('/holders/distribution'),

  getHolder: (address: string) =>
    fetchAPI<any>(`/holders/${address}`),

  // Analytics
  getOverview: () => fetchAPI<any>('/analytics/overview'),

  getVolume: (hours = 24) =>
    fetchAPI<any>(`/analytics/volume?hours=${hours}`),

  getBuySell: (hours = 24) =>
    fetchAPI<any>(`/analytics/buy-sell?hours=${hours}`),

  getHourlyVolume: (hours = 24) =>
    fetchAPI<{ hourly_data: any[] }>(`/analytics/hourly?hours=${hours}`),

  getWalletAnalysis: (address: string) =>
    fetchAPI<any>(`/analytics/wallet/${address}`),

  getTopWinners: (limit = 20) =>
    fetchAPI<{ wallets: any[] }>(`/analytics/top-winners?limit=${limit}`),

  getTopLosers: (limit = 20) =>
    fetchAPI<{ wallets: any[] }>(`/analytics/top-losers?limit=${limit}`),

  // Whales
  getWhales: (minBalance = 100000, limit = 50) =>
    fetchAPI<{ whales: any[]; count: number }>(
      `/whales?min_balance=${minBalance}&limit=${limit}`
    ),

  getWhaleSummary: () => fetchAPI<any>('/whales/summary'),

  getWhaleConcentration: () => fetchAPI<any>('/whales/concentration'),

  getWhaleActivity: (hours = 24) =>
    fetchAPI<{ activity: any[] }>(`/whales/activity?hours=${hours}`),

  getAccumulators: (days = 7) =>
    fetchAPI<{ wallets: any[] }>(`/whales/accumulating?days=${days}`),

  getDistributors: (days = 7) =>
    fetchAPI<{ wallets: any[] }>(`/whales/distributing?days=${days}`),

  // Health
  getHealth: () => fetchAPI<any>('/health'),
};

export default api;
