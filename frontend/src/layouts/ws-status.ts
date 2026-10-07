import { createContext, useContext } from 'react';

interface WsStatusContextValue {
  wsConnected: boolean;
  setWsConnected: (connected: boolean) => void;
}

/**
 * Shared WebSocket status between AppLayout (top bar display)
 * and the page that actually owns the socket (ChatPage).
 * Prevents opening a second, duplicate connection.
 */
export const WsStatusContext = createContext<WsStatusContextValue>({
  wsConnected: false,
  setWsConnected: () => {},
});

export function useWsStatus() {
  return useContext(WsStatusContext);
}
