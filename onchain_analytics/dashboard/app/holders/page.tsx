'use client';

import { useState } from 'react';
import { HolderTable } from '@/components/HolderTable';
import { useHolders, useHolderDistribution } from '@/lib/hooks';
import { formatNumber } from '@/lib/utils';

export default function HoldersPage() {
  const [sort, setSort] = useState<'balance' | 'trade_count' | 'last_active'>('balance');
  const { data: holdersData } = useHolders({ limit: 100, sort });
  const { data: distribution } = useHolderDistribution();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Holders</h1>
        <div className="text-sm text-slate-500">
          Total: {holdersData?.total_holders?.toLocaleString() || '-'} holders
        </div>
      </div>

      {/* Distribution Stats */}
      {distribution && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {distribution.distribution?.map((tier: any) => (
            <div
              key={tier.tier}
              className="bg-white dark:bg-slate-800 rounded-xl p-4 shadow-sm"
            >
              <p className="text-sm text-slate-500 capitalize">{tier.tier}</p>
              <p className="text-xl font-bold">{tier.holder_count}</p>
              <p className="text-xs text-slate-400">
                {formatNumber(tier.total_balance, 0)} ACU
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Sort Options */}
      <div className="flex items-center space-x-2">
        <span className="text-sm text-slate-500">Sort by:</span>
        <div className="flex space-x-1 bg-slate-100 dark:bg-slate-800 rounded-lg p-1">
          {[
            { key: 'balance', label: 'Balance' },
            { key: 'trade_count', label: 'Trades' },
            { key: 'last_active', label: 'Activity' },
          ].map((option) => (
            <button
              key={option.key}
              onClick={() => setSort(option.key as any)}
              className={`px-3 py-1 text-sm rounded-md transition-colors ${
                sort === option.key
                  ? 'bg-white dark:bg-slate-700 shadow'
                  : 'text-slate-600 dark:text-slate-400'
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {/* Holders Table */}
      <HolderTable limit={50} />
    </div>
  );
}
