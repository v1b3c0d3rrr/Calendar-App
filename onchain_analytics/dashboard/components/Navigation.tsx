'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { useLiveData } from '@/lib/websocket';

const navItems = [
  { href: '/', label: 'Overview' },
  { href: '/trades', label: 'Trades' },
  { href: '/holders', label: 'Holders' },
  { href: '/whales', label: 'Whales' },
];

export function Navigation() {
  const pathname = usePathname();
  const { status } = useLiveData();

  const statusColor = {
    connected: 'bg-green-500',
    connecting: 'bg-yellow-500 animate-pulse',
    disconnected: 'bg-red-500',
  }[status];

  const statusLabel = {
    connected: 'Live',
    connecting: 'Connecting...',
    disconnected: 'Offline',
  }[status];

  return (
    <nav className="bg-white dark:bg-slate-800 shadow-sm border-b border-slate-200 dark:border-slate-700">
      <div className="container mx-auto px-4">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link href="/" className="flex items-center space-x-2">
            <div className="w-8 h-8 bg-acu-primary rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-sm">ACU</span>
            </div>
            <span className="font-semibold text-lg text-slate-900 dark:text-white">
              Analytics
            </span>
          </Link>

          {/* Nav Links */}
          <div className="flex items-center space-x-1">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                  pathname === item.href
                    ? 'bg-acu-primary text-white'
                    : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
                )}
              >
                {item.label}
              </Link>
            ))}
          </div>

          {/* Status indicators */}
          <div className="flex items-center space-x-3">
            <div className="flex items-center space-x-1.5">
              <span className={cn('w-2 h-2 rounded-full', statusColor)} />
              <span className="text-xs text-slate-500">{statusLabel}</span>
            </div>
            <span className="px-2 py-1 bg-yellow-100 text-yellow-800 text-xs font-medium rounded">
              BSC
            </span>
          </div>
        </div>
      </div>
    </nav>
  );
}
