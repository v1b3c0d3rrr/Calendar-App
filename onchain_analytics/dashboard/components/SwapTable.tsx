'use client';

import { useLatestSwaps } from '@/lib/hooks';
import { useLiveData } from '@/lib/websocket';
import {
  formatNumber,
  formatPrice,
  formatRelativeTime,
  shortenAddress,
  getTradeTypeColor,
  getTradeTypeBg,
  getBscScanTxUrl,
  cn,
} from '@/lib/utils';

interface SwapTableProps {
  limit?: number;
  showAddress?: boolean;
}

export function SwapTable({ limit = 10, showAddress = false }: SwapTableProps) {
  const { data: swaps, error, isLoading } = useLatestSwaps(limit);

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 dark:border-slate-700">
          <h3 className="font-semibold">Recent Trades</h3>
        </div>
        <div className="p-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="flex items-center space-x-4 py-3 animate-pulse">
              <div className="h-6 bg-slate-200 dark:bg-slate-700 rounded w-12"></div>
              <div className="h-6 bg-slate-200 dark:bg-slate-700 rounded w-24"></div>
              <div className="h-6 bg-slate-200 dark:bg-slate-700 rounded w-20"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm">
        <p className="text-red-500">Error loading trades</p>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden">
      <div className="p-4 border-b border-slate-200 dark:border-slate-700">
        <h3 className="font-semibold">Recent Trades</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-slate-50 dark:bg-slate-700/50">
            <tr className="text-left text-xs text-slate-500 uppercase">
              <th className="px-4 py-3 font-medium">Type</th>
              <th className="px-4 py-3 font-medium">Amount ACU</th>
              <th className="px-4 py-3 font-medium">Amount USD</th>
              <th className="px-4 py-3 font-medium">Price</th>
              <th className="px-4 py-3 font-medium">Time</th>
              {showAddress && <th className="px-4 py-3 font-medium">Tx</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
            {swaps?.map((swap: any, i: number) => (
              <tr
                key={swap.tx_hash + i}
                className="hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors"
              >
                <td className="px-4 py-3">
                  <span
                    className={cn(
                      'px-2 py-1 rounded text-xs font-medium uppercase',
                      getTradeTypeBg(swap.type),
                      getTradeTypeColor(swap.type)
                    )}
                  >
                    {swap.type}
                  </span>
                </td>
                <td className="px-4 py-3 tabular-nums">
                  {formatNumber(swap.amount_acu)}
                </td>
                <td className="px-4 py-3 tabular-nums">
                  ${formatNumber(swap.amount_usdt)}
                </td>
                <td className="px-4 py-3 tabular-nums">
                  {formatPrice(swap.price_usdt)}
                </td>
                <td className="px-4 py-3 text-slate-500 text-sm">
                  {formatRelativeTime(swap.timestamp)}
                </td>
                {showAddress && (
                  <td className="px-4 py-3">
                    <a
                      href={getBscScanTxUrl(swap.tx_hash)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-acu-primary hover:underline text-sm"
                    >
                      {shortenAddress(swap.tx_hash, 4)}
                    </a>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function SwapFeed({ limit = 5 }: { limit?: number }) {
  const { data: polledSwaps } = useLatestSwaps(limit, 2000);
  const { liveSwaps, status } = useLiveData();

  // Use WS swaps when connected, fallback to polling
  const swaps = status === 'connected' && liveSwaps.length > 0
    ? liveSwaps.slice(0, limit)
    : polledSwaps;

  return (
    <div className="space-y-2">
      {swaps?.map((swap: any, i: number) => (
        <div
          key={swap.tx_hash + i}
          className={cn(
            'flex items-center justify-between p-3 rounded-lg',
            getTradeTypeBg(swap.type)
          )}
        >
          <div className="flex items-center space-x-3">
            <span
              className={cn(
                'font-medium uppercase text-sm',
                getTradeTypeColor(swap.type)
              )}
            >
              {swap.type}
            </span>
            <span className="text-sm tabular-nums">
              {formatNumber(swap.amount_acu)} ACU
            </span>
          </div>
          <div className="text-right">
            <span className="text-sm font-medium">
              ${formatNumber(swap.amount_usdt)}
            </span>
            <span className="text-xs text-slate-500 ml-2">
              {formatRelativeTime(swap.timestamp)}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
