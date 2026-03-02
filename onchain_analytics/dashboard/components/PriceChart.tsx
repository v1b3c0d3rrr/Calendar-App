'use client';

import { useEffect, useRef } from 'react';
import { usePriceHistory } from '@/lib/hooks';
import {
  createChart,
  ColorType,
  type IChartApi,
  type UTCTimestamp,
} from 'lightweight-charts';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { formatTime } from '@/lib/utils';

interface PriceChartProps {
  interval?: string;
  limit?: number;
  height?: number;
}

export function PriceChart({ interval = '1h', limit = 48, height = 300 }: PriceChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const { data, isLoading, error } = usePriceHistory(interval, limit);

  useEffect(() => {
    if (!chartContainerRef.current || !data?.candles?.length) return;

    // Remove old chart
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(chartContainerRef.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#94a3b8',
        fontFamily: 'Inter, sans-serif',
        fontSize: 12,
      },
      grid: {
        vertLines: { color: 'rgba(55, 65, 81, 0.1)' },
        horzLines: { color: 'rgba(55, 65, 81, 0.1)' },
      },
      crosshair: {
        vertLine: { labelBackgroundColor: '#1e293b' },
        horzLine: { labelBackgroundColor: '#1e293b' },
      },
      rightPriceScale: {
        borderVisible: false,
      },
      timeScale: {
        borderVisible: false,
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    const candlestickSeries = chart.addCandlestickSeries({
      upColor: '#10B981',
      downColor: '#EF4444',
      borderUpColor: '#10B981',
      borderDownColor: '#EF4444',
      wickUpColor: '#10B981',
      wickDownColor: '#EF4444',
    });

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });

    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    const candles = data.candles.map((c: any) => ({
      time: (Math.floor(new Date(c.timestamp).getTime() / 1000)) as UTCTimestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    const volumes = data.candles.map((c: any) => ({
      time: (Math.floor(new Date(c.timestamp).getTime() / 1000)) as UTCTimestamp,
      value: c.volume_usdt,
      color: c.close >= c.open ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)',
    }));

    candlestickSeries.setData(candles);
    volumeSeries.setData(volumes);

    chart.timeScale().fitContent();

    // Resize observer
    const resizeObserver = new ResizeObserver(() => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    });
    resizeObserver.observe(chartContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [data, height]);

  if (isLoading) {
    return (
      <div
        className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm animate-pulse"
        style={{ height: height + 60 }}
      >
        <div className="h-full bg-slate-200 dark:bg-slate-700 rounded"></div>
      </div>
    );
  }

  if (error || !data?.candles?.length) {
    return (
      <div
        className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm flex items-center justify-center"
        style={{ height: height + 60 }}
      >
        <p className="text-slate-500">No chart data available</p>
      </div>
    );
  }

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
      <div ref={chartContainerRef} />
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
