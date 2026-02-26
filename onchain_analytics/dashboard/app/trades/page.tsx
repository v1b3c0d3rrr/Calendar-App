'use client';

import { useState } from 'react';
import { useSwaps, useLargeSwaps } from '@/lib/hooks';
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

export default function TradesPage() {
  const [filter, setFilter] = useState<'all' | 'buy' | 'sell'>('all');
  const [hours, setHours] = useState(24);

  const { data: swapsData, isLoading } = useSwaps({
    hours,
    type: filter === 'all' ? undefined : filter,
    limit: 100,
  });

  const { data: largeSwaps } = useLargeSwaps(24, 1000);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Trades</h1>
        <div className="flex items-center space-x-4">
          {/* Time filter */}
          <div className="flex space-x-1 bg-slate-100 dark:bg-slate-800 rounded-lg p-1">
            {[6, 12, 24, 48].map((h) => (
              <button
                key={h}
                onClick={() => setHours(h)}
                className={cn(
                  'px-3 py-1 text-sm rounded-md transition-colors',
                  hours === h
                    ? 'bg-white dark:bg-slate-700 shadow'
                    : 'text-slate-600 dark:text-slate-400'
                )}
              >
                {h}h
              </button>
            ))}
          </div>
          {/* Type filter */}
          <div className="flex space-x-1 bg-slate-100 dark:bg-slate-800 rounded-lg p-1">
            {(['all', 'buy', 'sell'] as const).map((type) => (
              <button
                key={type}
                onClick={() => setFilter(type)}
                className={cn(
                  'px-3 py-1 text-sm rounded-md capitalize transition-colors',
                  filter === type
                    ? 'bg-white dark:bg-slate-700 shadow'
                    : 'text-slate-600 dark:text-slate-400'
                )}
              >
                {type}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm">
          <p className="text-sm text-slate-500">Total Trades</p>
          <p className="text-2xl font-bold">{swapsData?.total || 0}</p>
        </div>
        <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm">
          <p className="text-sm text-slate-500">Showing</p>
          <p className="text-2xl font-bold">{swapsData?.count || 0}</p>
        </div>
        <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm">
          <p className="text-sm text-slate-500">Large Trades (24h)</p>
          <p className="text-2xl font-bold">{largeSwaps?.length || 0}</p>
        </div>
        <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm">
          <p className="text-sm text-slate-500">Period</p>
          <p className="text-2xl font-bold">{hours}h</p>
        </div>
      </div>

      {/* Trades Table */}
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-50 dark:bg-slate-700/50">
              <tr className="text-left text-xs text-slate-500 uppercase">
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Amount ACU</th>
                <th className="px-4 py-3 font-medium">Amount USD</th>
                <th className="px-4 py-3 font-medium">Price</th>
                <th className="px-4 py-3 font-medium">Sender</th>
                <th className="px-4 py-3 font-medium">Recipient</th>
                <th className="px-4 py-3 font-medium">Time</th>
                <th className="px-4 py-3 font-medium">Tx</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
              {isLoading ? (
                [...Array(10)].map((_, i) => (
                  <tr key={i}>
                    <td colSpan={8} className="px-4 py-3">
                      <div className="h-6 bg-slate-200 dark:bg-slate-700 rounded animate-pulse"></div>
                    </td>
                  </tr>
                ))
              ) : (
                swapsData?.swaps?.map((swap: any) => (
                  <tr
                    key={swap.tx_hash}
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
                    <td className="px-4 py-3">
                      <span className="font-mono text-sm">
                        {shortenAddress(swap.sender, 4)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-mono text-sm">
                        {shortenAddress(swap.recipient, 4)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-500 text-sm">
                      {formatRelativeTime(swap.timestamp)}
                    </td>
                    <td className="px-4 py-3">
                      <a
                        href={getBscScanTxUrl(swap.tx_hash)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-acu-primary hover:underline text-sm"
                      >
                        View
                      </a>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
