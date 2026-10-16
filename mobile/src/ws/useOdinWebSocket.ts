import { useEffect, useRef, useState, useCallback } from 'react';
import type { OdinEvent, ClientMessage } from '../types/websocket';
import { wsUrl } from '../lib/config';

interface UseOdinWebSocketOptions {
  conversationId: string | null;
  onEvent?: (event: OdinEvent) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: unknown) => void;
}

interface UseOdinWebSocketReturn {
  isConnected: boolean;
  sendMessage: (content: string) => void;
  sendStop: () => void;
  sendPing: () => void;
  error: Error | null;
}

const RECONNECT_DELAY_MS = 2000;
const PING_INTERVAL_MS = 30000;
const MAX_ATTEMPTS = 5;

/**
 * WebSocket service for a single ODIN conversation (ported from the web
 * panel). Uses the global WebSocket available in React Native.
 */
export function useOdinWebSocket({
  conversationId,
  onEvent,
  onConnect,
  onDisconnect,
  onError,
}: UseOdinWebSocketOptions): UseOdinWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const closedByClientRef = useRef(false);
  const attemptsRef = useRef(0);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  // Latest callbacks, kept in a ref so the socket isn't re-created when they
  // change identity. Refs must not be written during render, so this runs in an
  // effect (which executes before any async socket event fires).
  const callbacksRef = useRef({ onEvent, onConnect, onDisconnect, onError });
  useEffect(() => {
    callbacksRef.current = { onEvent, onConnect, onDisconnect, onError };
  });

  // Lets the reconnect timer call the latest connect() without referencing the
  // `connect` const before its declaration.
  const connectRef = useRef<() => void>(() => {});

  const clearTimers = useCallback(() => {
    if (reconnectTimeoutRef.current !== null) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (pingIntervalRef.current !== null) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
  }, []);

  const disconnect = useCallback(() => {
    closedByClientRef.current = true;
    clearTimers();
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onmessage = null;
      wsRef.current.onerror = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
  }, [clearTimers]);

  const connect = useCallback(() => {
    if (!conversationId) return;
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    const url = wsUrl(conversationId);
    if (!url) return;

    closedByClientRef.current = false;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        attemptsRef.current = 0;
        setIsConnected(true);
        setError(null);
        callbacksRef.current.onConnect?.();
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' } satisfies ClientMessage));
          }
        }, PING_INTERVAL_MS);
      };

      ws.onmessage = (event) => {
        try {
          const data: OdinEvent = JSON.parse(String(event.data));
          callbacksRef.current.onEvent?.(data);
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        if (pingIntervalRef.current !== null) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = null;
        }
        callbacksRef.current.onDisconnect?.();

        if (!closedByClientRef.current && attemptsRef.current < MAX_ATTEMPTS) {
          attemptsRef.current += 1;
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectTimeoutRef.current = null;
            connectRef.current();
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

  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  const sendMessage = useCallback((content: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const message: ClientMessage = { type: 'message', content };
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  const sendStop = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const message: ClientMessage = { type: 'stop' };
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  const sendPing = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'ping' } satisfies ClientMessage));
    }
  }, []);

  // Connect when a conversation is selected. The cleanup (which also tears the
  // socket down when switching away or unmounting) covers the null case, so no
  // reset branch is needed here. Connecting is an intentional subscription to
  // an external system; the resulting connection-state updates are expected.
  /* eslint-disable react-hooks/set-state-in-effect -- subscribing to the WebSocket for the active conversation */
  useEffect(() => {
    if (!conversationId) return;
    attemptsRef.current = 0;
    connect();
    return () => disconnect();
  }, [conversationId, connect, disconnect]);
  /* eslint-enable react-hooks/set-state-in-effect */

  return {
    isConnected,
    sendMessage,
    sendStop,
    sendPing,
    error,
  };
}
