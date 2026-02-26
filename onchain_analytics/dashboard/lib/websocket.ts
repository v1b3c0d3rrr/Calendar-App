'use client';

import { useEffect, useRef, useState, useCallback } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const WS_URL = API_URL.replace(/^http/, 'ws') + '/ws/live';

/** Message types from the server */
export interface WsPriceMessage {
  type: 'price';
  data: {
    price: number;
    timestamp: string;
    change_pct: number;
  };
}

export interface WsSwapMessage {
  type: 'swap';
  data: {
    id: number;
    tx_hash: string;
    timestamp: string;
    type: 'buy' | 'sell';
    amount_acu: number;
    amount_usdt: number;
    price_usdt: number;
    sender: string;
  };
}

export interface WsAlertMessage {
  type: 'alert';
  data: {
    kind: string;
    change_pct: number;
    price: number;
    timestamp: string;
  };
}

export type WsMessage = WsPriceMessage | WsSwapMessage | WsAlertMessage;

export type WsStatus = 'connecting' | 'connected' | 'disconnected';

/**
 * React hook for WebSocket connection to /ws/live.
 * Auto-reconnects on disconnect with exponential backoff.
 * Returns latest price, recent swaps, alerts, and connection status.
 */
export function useLiveData() {
  const [status, setStatus] = useState<WsStatus>('disconnected');
  const [livePrice, setLivePrice] = useState<WsPriceMessage['data'] | null>(null);
  const [liveSwaps, setLiveSwaps] = useState<WsSwapMessage['data'][]>([]);
  const [alerts, setAlerts] = useState<WsAlertMessage['data'][]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout>>();

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus('connecting');
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus('connected');
      retryCountRef.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const msg: WsMessage = JSON.parse(event.data);

        switch (msg.type) {
          case 'price':
            setLivePrice(msg.data);
            break;

          case 'swap':
            setLiveSwaps((prev) => [msg.data, ...prev].slice(0, 20));
            break;

          case 'alert':
            setAlerts((prev) => [msg.data, ...prev].slice(0, 10));
            break;
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      setStatus('disconnected');
      wsRef.current = null;

      // Reconnect with exponential backoff (1s, 2s, 4s, 8s... max 30s)
      const delay = Math.min(1000 * 2 ** retryCountRef.current, 30000);
      retryCountRef.current++;
      retryTimerRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    connect();

    return () => {
      wsRef.current?.close();
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    };
  }, [connect]);

  const clearAlerts = useCallback(() => setAlerts([]), []);

  return { status, livePrice, liveSwaps, alerts, clearAlerts };
}
