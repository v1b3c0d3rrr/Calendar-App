'use client';

import { usePrice, usePriceStats } from '@/lib/hooks';
import { useLiveData } from '@/lib/websocket';
import { formatPrice, formatPercent, getPriceChangeColor, cn } from '@/lib/utils';

interface PriceDisplayProps {
  size?: 'sm' | 'md' | 'lg';
}

export function PriceDisplay({ size = 'lg' }: PriceDisplayProps) {
  const { data: priceData, error: priceError } = usePrice();
  const { data: statsData } = usePriceStats(24);
  const { livePrice } = useLiveData();

  // Prefer WS price if available, fallback to polling
  const price = livePrice?.price ?? priceData?.price;
  const change = statsData?.change_pct;

  const sizeClasses = {
    sm: 'text-xl',
    md: 'text-3xl',
    lg: 'text-5xl',
  };

  if (priceError) {
    return (
      <div className="text-red-500">
        Error loading price
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="flex items-baseline space-x-3">
        <span className={cn('font-bold tabular-nums', sizeClasses[size])}>
          {price ? formatPrice(price) : '-'}
        </span>
        {change !== null && change !== undefined && (
          <span className={cn('text-lg font-medium', getPriceChangeColor(change))}>
            {formatPercent(change)}
          </span>
        )}
      </div>
      {statsData && (
        <div className="flex items-center space-x-4 mt-2 text-sm text-slate-500">
          <span>H: {formatPrice(statsData.high ?? 0)}</span>
          <span>L: {formatPrice(statsData.low ?? 0)}</span>
        </div>
      )}
    </div>
  );
}

export function PriceCard() {
  const { data: priceData, isLoading } = usePrice();
  const { data: statsData } = usePriceStats(24);
  const { livePrice } = useLiveData();

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-slate-800 rounded-xl p-6 shadow-sm animate-pulse">
        <div className="h-8 bg-slate-200 dark:bg-slate-700 rounded w-32 mb-2"></div>
        <div className="h-12 bg-slate-200 dark:bg-slate-700 rounded w-48"></div>
      </div>
    );
  }

  // Prefer WS price if available
  const price = livePrice?.price ?? priceData?.price;
  const change = statsData?.change_pct;

  return (
    <div className="bg-white dark:bg-slate-800 rounded-xl p-6 shadow-sm">
      <div className="text-sm text-slate-500 dark:text-slate-400 mb-1">
        ACU Price
      </div>
      <div className="flex items-baseline space-x-3">
        <span className="text-4xl font-bold tabular-nums">
          {price ? formatPrice(price) : '-'}
        </span>
        {change !== null && change !== undefined && (
          <span className={cn('text-lg font-semibold', getPriceChangeColor(change))}>
            {formatPercent(change)}
          </span>
        )}
      </div>
      {statsData && (
        <div className="flex items-center space-x-4 mt-3 text-sm text-slate-500">
          <div>
            <span className="text-slate-400">24h High:</span>{' '}
            <span className="font-medium">{formatPrice(statsData.high ?? 0)}</span>
          </div>
          <div>
            <span className="text-slate-400">24h Low:</span>{' '}
            <span className="font-medium">{formatPrice(statsData.low ?? 0)}</span>
          </div>
        </div>
      )}
    </div>
  );
}
