'use client';

import { useWhaleSummary, useWhaleActivity, useAccumulators, useDistributors } from '@/lib/hooks';
import { StatCard, StatGrid } from '@/components/StatCard';
import {
  formatNumber,
  formatCurrency,
  formatRelativeTime,
  shortenAddress,
  getTradeTypeColor,
  getBscScanAddressUrl,
  getBscScanTxUrl,
  cn,
} from '@/lib/utils';

export default function WhalesPage() {
  const { data: summary, isLoading } = useWhaleSummary();
  const { data: activityData } = useWhaleActivity(24);
  const { data: accumulatorsData } = useAccumulators(7);
  const { data: distributorsData } = useDistributors(7);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold">Whale Tracker</h1>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm animate-pulse">
              <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-20 mb-2"></div>
              <div className="h-8 bg-slate-200 dark:bg-slate-700 rounded w-16"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const concentration = summary?.concentration;
  const activity = summary?.activity_24h;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Whale Tracker</h1>
        <div className={cn(
          'px-3 py-1 rounded-full text-sm font-medium',
          activity?.sentiment === 'bullish' ? 'bg-buy/10 text-buy' :
          activity?.sentiment === 'bearish' ? 'bg-sell/10 text-sell' :
          'bg-slate-100 text-slate-600'
        )}>
          {activity?.sentiment || 'neutral'} sentiment
        </div>
      </div>

      {/* Concentration Stats */}
      <StatGrid columns={4}>
        <StatCard
          title="Whale Count"
          value={concentration?.whales?.count || 0}
          subtitle={`>${formatNumber(concentration?.whales?.threshold || 100000, 0)} ACU`}
        />
        <StatCard
          title="Top 10 Hold"
          value={`${concentration?.top_10?.percentage?.toFixed(1) || 0}%`}
          subtitle={formatNumber(concentration?.top_10?.total_balance || 0, 0) + ' ACU'}
        />
        <StatCard
          title="Top 50 Hold"
          value={`${concentration?.top_50?.percentage?.toFixed(1) || 0}%`}
          subtitle={formatNumber(concentration?.top_50?.total_balance || 0, 0) + ' ACU'}
        />
        <StatCard
          title="Whale Activity (24h)"
          value={activity?.total_trades || 0}
          subtitle={`${activity?.buys || 0} buys, ${activity?.sells || 0} sells`}
        />
      </StatGrid>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Whales */}
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden">
          <div className="p-4 border-b border-slate-200 dark:border-slate-700">
            <h3 className="font-semibold">Top Whales</h3>
          </div>
          <div className="divide-y divide-slate-200 dark:divide-slate-700">
            {summary?.top_whales?.map((whale: any, i: number) => (
              <div key={whale.address} className="p-4 flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <span className="text-slate-400 w-6">{i + 1}</span>
                  <div>
                    <a
                      href={getBscScanAddressUrl(whale.address)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-acu-primary hover:underline font-mono text-sm"
                    >
                      {shortenAddress(whale.address, 6)}
                    </a>
                    {whale.label && (
                      <span className="ml-2 text-xs text-slate-500">{whale.label}</span>
                    )}
                  </div>
                </div>
                <div className="text-right">
                  <p className="font-medium">{formatNumber(whale.balance, 0)} ACU</p>
                  <p className="text-sm text-slate-500">{whale.percentage_of_supply?.toFixed(2)}%</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Whale Activity */}
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden">
          <div className="p-4 border-b border-slate-200 dark:border-slate-700">
            <h3 className="font-semibold">Recent Whale Activity</h3>
          </div>
          <div className="divide-y divide-slate-200 dark:divide-slate-700 max-h-96 overflow-y-auto">
            {activityData?.activity?.slice(0, 10).map((trade: any, i: number) => (
              <div key={trade.tx_hash + i} className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <span className={cn(
                      'px-2 py-0.5 rounded text-xs font-medium uppercase',
                      trade.action === 'buy' ? 'bg-buy/10 text-buy' : 'bg-sell/10 text-sell'
                    )}>
                      {trade.action}
                    </span>
                    <span className="font-mono text-sm">
                      {shortenAddress(trade.whale_address, 4)}
                    </span>
                  </div>
                  <span className="text-sm text-slate-500">
                    {formatRelativeTime(trade.timestamp)}
                  </span>
                </div>
                <div className="mt-2 flex justify-between text-sm">
                  <span>{formatNumber(trade.amount_acu)} ACU</span>
                  <span className="text-slate-500">{formatCurrency(trade.amount_usdt)}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Accumulating vs Distributing */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Accumulating */}
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden">
          <div className="p-4 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
            <h3 className="font-semibold text-buy">Accumulating (7d)</h3>
            <span className="text-sm text-slate-500">Net buyers</span>
          </div>
          <div className="divide-y divide-slate-200 dark:divide-slate-700">
            {accumulatorsData?.wallets?.slice(0, 5).map((wallet: any) => (
              <div key={wallet.address} className="p-4 flex items-center justify-between">
                <a
                  href={getBscScanAddressUrl(wallet.address)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-acu-primary hover:underline font-mono text-sm"
                >
                  {shortenAddress(wallet.address, 6)}
                </a>
                <div className="text-right">
                  <p className="font-medium text-buy">+{formatNumber(wallet.net_accumulated, 0)}</p>
                  <p className="text-xs text-slate-500">Balance: {formatNumber(wallet.current_balance, 0)}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Distributing */}
        <div className="bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden">
          <div className="p-4 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
            <h3 className="font-semibold text-sell">Distributing (7d)</h3>
            <span className="text-sm text-slate-500">Net sellers</span>
          </div>
          <div className="divide-y divide-slate-200 dark:divide-slate-700">
            {distributorsData?.wallets?.slice(0, 5).map((wallet: any) => (
              <div key={wallet.address} className="p-4 flex items-center justify-between">
                <a
                  href={getBscScanAddressUrl(wallet.address)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-acu-primary hover:underline font-mono text-sm"
                >
                  {shortenAddress(wallet.address, 6)}
                </a>
                <div className="text-right">
                  <p className="font-medium text-sell">-{formatNumber(wallet.net_distributed, 0)}</p>
                  <p className="text-xs text-slate-500">Balance: {formatNumber(wallet.current_balance, 0)}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
