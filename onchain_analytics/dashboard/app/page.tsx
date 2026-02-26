'use client';

import { PriceCard } from '@/components/PriceDisplay';
import { StatCard, StatGrid } from '@/components/StatCard';
import { SwapTable, SwapFeed } from '@/components/SwapTable';
import { PriceChart, VolumeChart } from '@/components/PriceChart';
import { useMarketOverview } from '@/lib/hooks';
import { formatNumber, formatCurrency } from '@/lib/utils';

export default function OverviewPage() {
  const { data: overview, isLoading } = useMarketOverview();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">ACU Token Analytics</h1>
        <div className="text-sm text-slate-500">
          Real-time data from BSC
        </div>
      </div>

      {/* Price and Stats */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <PriceCard />
        </div>
        <div className="lg:col-span-2">
          <StatGrid columns={3}>
            <StatCard
              title="24h Volume"
              value={overview?.volume?.volume_24h_usdt || 0}
              format="currency"
            />
            <StatCard
              title="24h Trades"
              value={overview?.volume?.trades_24h || 0}
              format="number"
            />
            <StatCard
              title="Holders"
              value={overview?.holders?.total_holders || 0}
              format="number"
            />
          </StatGrid>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <PriceChart interval="1h" limit={48} height={350} />
        </div>
        <div className="space-y-4">
          <VolumeChart hours={24} />
          {/* Buy/Sell Stats */}
          <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm">
            <h3 className="font-semibold mb-3">Trading Activity (24h)</h3>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-slate-500">Buys</span>
                <span className="text-buy font-medium">
                  {overview?.trading?.buy_count_24h || 0}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Sells</span>
                <span className="text-sell font-medium">
                  {overview?.trading?.sell_count_24h || 0}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Buy/Sell Ratio</span>
                <span className="font-medium">
                  {overview?.trading?.buy_sell_ratio?.toFixed(2) || '-'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Avg Trade</span>
                <span className="font-medium">
                  {formatCurrency(overview?.trading?.avg_trade_usdt || 0)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Net Flow</span>
                <span className={overview?.trading?.net_flow_usdt >= 0 ? 'text-buy' : 'text-sell'}>
                  {formatCurrency(overview?.trading?.net_flow_usdt || 0)}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Trades and Live Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <SwapTable limit={10} showAddress={true} />
        </div>
        <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm">
          <h3 className="font-semibold mb-4">Live Feed</h3>
          <SwapFeed limit={8} />
        </div>
      </div>
    </div>
  );
}
