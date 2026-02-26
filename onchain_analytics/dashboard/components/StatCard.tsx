'use client';

import { cn, formatNumber, formatCurrency, formatPercent, getPriceChangeColor } from '@/lib/utils';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  change?: number | null;
  format?: 'number' | 'currency' | 'percent' | 'none';
  icon?: React.ReactNode;
  className?: string;
}

export function StatCard({
  title,
  value,
  subtitle,
  change,
  format = 'none',
  icon,
  className,
}: StatCardProps) {
  const formattedValue = () => {
    if (typeof value === 'string') return value;
    switch (format) {
      case 'currency':
        return formatCurrency(value);
      case 'percent':
        return formatPercent(value);
      case 'number':
        return formatNumber(value);
      default:
        return value.toLocaleString();
    }
  };

  return (
    <div className={cn(
      'bg-white dark:bg-slate-800 rounded-xl p-5 shadow-sm',
      className
    )}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-slate-500 dark:text-slate-400">{title}</p>
          <p className="text-2xl font-bold mt-1 tabular-nums">{formattedValue()}</p>
          {subtitle && (
            <p className="text-sm text-slate-400 mt-1">{subtitle}</p>
          )}
          {change !== null && change !== undefined && (
            <p className={cn('text-sm font-medium mt-1', getPriceChangeColor(change))}>
              {formatPercent(change)}
            </p>
          )}
        </div>
        {icon && (
          <div className="p-2 bg-slate-100 dark:bg-slate-700 rounded-lg">
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}

interface StatGridProps {
  children: React.ReactNode;
  columns?: 2 | 3 | 4;
}

export function StatGrid({ children, columns = 4 }: StatGridProps) {
  const gridCols = {
    2: 'grid-cols-1 sm:grid-cols-2',
    3: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
    4: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4',
  };

  return (
    <div className={cn('grid gap-4', gridCols[columns])}>
      {children}
    </div>
  );
}
