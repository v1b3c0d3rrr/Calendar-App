'use client';

import { usePriceHistory } from '@/lib/hooks';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { formatPrice, formatTime } from '@/lib/utils';

interface PriceChartProps {
  interval?: string;
  limit?: number;
  height?: number;
}

export function PriceChart({ interval = '1h', limit = 48, height = 300 }: PriceChartProps) {
  const { data, isLoading, error } = usePriceHistory(interval, limit);

  if (isLoading) {
    return (
      <div
        className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm animate-pulse"
        style={{ height }}
      >
        <div className="h-full bg-slate-200 dark:bg-slate-700 rounded"></div>
      </div>
    );
  }

  if (error || !data?.candles?.length) {
    return (
      <div
        className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm flex items-center justify-center"
        style={{ height }}
      >
        <p className="text-slate-500">No chart data available</p>
      </div>
    );
  }

  const chartData = data.candles.map((c: any) => ({
    time: new Date(c.timestamp).getTime(),
    price: c.close,
    volume: c.volume_usdt,
  }));

  // Determine if price went up or down
  const firstPrice = chartData[0]?.price || 0;
  const lastPrice = chartData[chartData.length - 1]?.price || 0;
  const isUp = lastPrice >= firstPrice;

  return (
    <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold">Price Chart</h3>
        <div className="flex space-x-2">
          {['1h', '4h', '1d'].map((i) => (
            <button
              key={i}
              className={`px-3 py-1 text-xs rounded ${
                interval === i
                  ? 'bg-acu-primary text-white'
                  : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300'
              }`}
            >
              {i}
            </button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={chartData}>
          <defs>
            <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="5%"
                stopColor={isUp ? '#10B981' : '#EF4444'}
                stopOpacity={0.3}
              />
              <stop
                offset="95%"
                stopColor={isUp ? '#10B981' : '#EF4444'}
                stopOpacity={0}
              />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" opacity={0.1} />
          <XAxis
            dataKey="time"
            tickFormatter={(t) => formatTime(new Date(t).toISOString())}
            stroke="#94a3b8"
            fontSize={12}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            domain={['auto', 'auto']}
            tickFormatter={(v) => formatPrice(v)}
            stroke="#94a3b8"
            fontSize={12}
            tickLine={false}
            axisLine={false}
            width={80}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1e293b',
              border: 'none',
              borderRadius: '8px',
              color: '#fff',
            }}
            labelFormatter={(t) => new Date(t).toLocaleString()}
            formatter={(value: number) => [formatPrice(value), 'Price']}
          />
          <Area
            type="monotone"
            dataKey="price"
            stroke={isUp ? '#10B981' : '#EF4444'}
            fill="url(#priceGradient)"
            strokeWidth={2}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function VolumeChart({ hours = 24 }: { hours?: number }) {
  const { data } = usePriceHistory('1h', hours);

  if (!data?.candles?.length) {
    return null;
  }

  const chartData = data.candles.map((c: any) => ({
    time: new Date(c.timestamp).getTime(),
    volume: c.volume_usdt,
    trades: c.trade_count,
  }));

  return (
    <div className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm">
      <h3 className="font-semibold mb-4">Volume (24h)</h3>
      <ResponsiveContainer width="100%" height={150}>
        <AreaChart data={chartData}>
          <XAxis
            dataKey="time"
            tickFormatter={(t) => formatTime(new Date(t).toISOString())}
            stroke="#94a3b8"
            fontSize={10}
            tickLine={false}
            axisLine={false}
          />
          <YAxis hide />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1e293b',
              border: 'none',
              borderRadius: '8px',
              color: '#fff',
            }}
            formatter={(value: number) => ['$' + value.toLocaleString(), 'Volume']}
          />
          <Area
            type="monotone"
            dataKey="volume"
            stroke="#3B82F6"
            fill="#3B82F6"
            fillOpacity={0.2}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
