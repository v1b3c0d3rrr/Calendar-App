'use client';

import { useTopHolders } from '@/lib/hooks';
import {
  formatNumber,
  shortenAddress,
  formatRelativeTime,
  getBscScanAddressUrl,
} from '@/lib/utils';

interface HolderTableProps {
  limit?: number;
}

export function HolderTable({ limit = 20 }: HolderTableProps) {
  const { data: holders, isLoading, error } = useTopHolders(limit);

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 dark:border-slate-700">
          <h3 className="font-semibold">Top Holders</h3>
        </div>
        <div className="p-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="flex items-center space-x-4 py-3 animate-pulse">
              <div className="h-6 bg-slate-200 dark:bg-slate-700 rounded w-8"></div>
              <div className="h-6 bg-slate-200 dark:bg-slate-700 rounded w-32"></div>
              <div className="h-6 bg-slate-200 dark:bg-slate-700 rounded w-24"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm">
        <p className="text-red-500">Error loading holders</p>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden">
      <div className="p-4 border-b border-slate-200 dark:border-slate-700">
        <h3 className="font-semibold">Top Holders</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-slate-50 dark:bg-slate-700/50">
            <tr className="text-left text-xs text-slate-500 uppercase">
              <th className="px-4 py-3 font-medium">#</th>
              <th className="px-4 py-3 font-medium">Address</th>
              <th className="px-4 py-3 font-medium text-right">Balance</th>
              <th className="px-4 py-3 font-medium text-right">% Supply</th>
              <th className="px-4 py-3 font-medium text-right">Trades</th>
              <th className="px-4 py-3 font-medium">Last Active</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
            {holders?.map((holder: any, i: number) => (
              <tr
                key={holder.address}
                className="hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors"
              >
                <td className="px-4 py-3 text-slate-500">{i + 1}</td>
                <td className="px-4 py-3">
                  <a
                    href={getBscScanAddressUrl(holder.address)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-acu-primary hover:underline font-mono text-sm"
                  >
                    {shortenAddress(holder.address, 6)}
                  </a>
                  {holder.label && (
                    <span className="ml-2 px-2 py-0.5 bg-slate-100 dark:bg-slate-700 text-xs rounded">
                      {holder.label}
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {formatNumber(holder.balance, 0)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {holder.percentage?.toFixed(2)}%
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {holder.trade_count}
                </td>
                <td className="px-4 py-3 text-slate-500 text-sm">
                  {formatRelativeTime(holder.last_active)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function HolderDistributionChart() {
  // Could add a pie/bar chart for holder distribution
  return null;
}
