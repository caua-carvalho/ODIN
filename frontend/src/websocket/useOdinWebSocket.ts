import { useEffect, useRef, useState, useCallback } from 'react';
import type { OdinEvent, ClientMessage } from '../types/websocket';

interface UseOdinWebSocketOptions {
  conversationId: string | null;
  onEvent?: (event: OdinEvent) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Event) => void;
}

interface UseOdinWebSocketReturn {
  isConnected: boolean;
  sendMessage: (content: string) => void;
  sendPing: () => void;
  lastEvent: OdinEvent | null;
  error: Error | null;
}

const RECONNECT_DELAY_MS = 2000;
const PING_INTERVAL_MS = 30000;

/**
 * Dedicated WebSocket service for a single ODIN conversation.
 * - controlled reconnect (skips intentional closes, single timer, max 5 attempts)
 * - callbacks kept in refs so inline handlers never thrash the connection
 * - periodic ping keeps the connection alive
 */
export function useOdinWebSocket({
  conversationId,
  onEvent,
  onConnect,
  onDisconnect,
  onError,
}: UseOdinWebSocketOptions): UseOdinWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const closedByClientRef = useRef(false);
  const attemptsRef = useRef(0);
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<OdinEvent | null>(null);
  const [error, setError] = useState<Error | null>(null);

  // Keep latest callbacks in refs so connection lifecycle is stable
  const callbacksRef = useRef({ onEvent, onConnect, onDisconnect, onError });
  callbacksRef.current = { onEvent, onConnect, onDisconnect, onError };

  const disconnect = useCallback(() => {
    closedByClientRef.current = true;
    if (reconnectTimeoutRef.current !== null) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onmessage = null;
      wsRef.current.onerror = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
  }, []);

  const connect = useCallback(() => {
    if (!conversationId) return;
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    closedByClientRef.current = false;

    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = import.meta.env.VITE_WS_HOST || window.location.host;
      const ws = new WebSocket(`${protocol}//${host}/api/ws/${conversationId}`);
      wsRef.current = ws;

      ws.onopen = () => {
        attemptsRef.current = 0;
        setIsConnected(true);
        setError(null);
        callbacksRef.current.onConnect?.();
      };

      ws.onmessage = (event) => {
        try {
          const data: OdinEvent = JSON.parse(event.data);
          setLastEvent(data);
          callbacksRef.current.onEvent?.(data);
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        callbacksRef.current.onDisconnect?.();

        // No reconnect after intentional close, and never infinitely
        if (
          !closedByClientRef.current &&
          conversationId &&
          attemptsRef.current < 5
        ) {
          attemptsRef.current += 1;
          reconnectTimeoutRef.current = window.setTimeout(() => {
            reconnectTimeoutRef.current = null;
            connect();
          }, RECONNECT_DELAY_MS);
        }
      };

      ws.onerror = (err) => {
        setError(new Error('WebSocket connection error'));
        callbacksRef.current.onError?.(err);
      };
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to create WebSocket'));
    }
  }, [conversationId]);

  const sendMessage = useCallback((content: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const message: ClientMessage = { type: 'message', content };
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  const sendPing = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'ping' }));
    }
  }, []);

  useEffect(() => {
    if (conversationId) {
      attemptsRef.current = 0;
      connect();
    } else {
      disconnect();
    }

    return () => {
      disconnect();
    };
  }, [conversationId, connect, disconnect]);

  // Periodic ping to keep the connection alive
  useEffect(() => {
    if (!isConnected) return;
    const interval = setInterval(() => sendPing(), PING_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [isConnected, sendPing]);

  return {
    isConnected,
    sendMessage,
    sendPing,
    lastEvent,
    error,
  };
}
