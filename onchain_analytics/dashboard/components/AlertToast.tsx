'use client';

import { useEffect, useState } from 'react';
import { useLiveData } from '@/lib/websocket';
import { formatPrice, cn } from '@/lib/utils';

interface Toast {
  id: number;
  message: string;
  type: 'up' | 'down';
  timestamp: string;
}

let toastId = 0;

export function AlertToast() {
  const { alerts } = useLiveData();
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Convert new alerts into toasts
  useEffect(() => {
    if (alerts.length === 0) return;

    const latest = alerts[0];
    const isUp = latest.change_pct > 0;
    const direction = isUp ? 'up' : 'down';
    const arrow = isUp ? '+' : '';

    const toast: Toast = {
      id: ++toastId,
      message: `Price ${direction} ${arrow}${latest.change_pct.toFixed(1)}% — ${formatPrice(latest.price)}`,
      type: direction,
      timestamp: latest.timestamp,
    };

    setToasts((prev) => [toast, ...prev].slice(0, 3));

    // Auto-dismiss after 8 seconds
    const timer = setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== toast.id));
    }, 8000);

    return () => clearTimeout(timer);
  }, [alerts]);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={cn(
            'px-4 py-3 rounded-lg shadow-lg text-sm font-medium animate-slide-in',
            'border backdrop-blur-sm max-w-xs',
            toast.type === 'up'
              ? 'bg-green-50 border-green-200 text-green-800'
              : 'bg-red-50 border-red-200 text-red-800'
          )}
        >
          <div className="flex items-center justify-between gap-3">
            <span>{toast.type === 'up' ? '\u25B2' : '\u25BC'} {toast.message}</span>
            <button
              onClick={() => setToasts((prev) => prev.filter((t) => t.id !== toast.id))}
              className="text-slate-400 hover:text-slate-600 text-lg leading-none"
            >
              &times;
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
