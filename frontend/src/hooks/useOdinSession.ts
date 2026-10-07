import { useState, useCallback, useRef, useEffect } from 'react';
import { useOdinWebSocket } from '../websocket/useOdinWebSocket';
import { conversationsApi } from '../api/conversations';
import type { Message } from '../types/conversation';
import type { OdinEvent, PermissionRequestEvent } from '../types/websocket';
import type { ToolExecutionData } from '../components/ToolExecution';

export type SessionState = 'idle' | 'thinking' | 'waiting_auth' | 'streaming' | 'error';

/** Unified timeline entries: persisted messages, tool runs and permission intercepts, in arrival order. */
export type TimelineEntry =
  | { kind: 'message'; id: string; message: Message }
  | { kind: 'tool'; id: string; execution: ToolExecutionData }
  | { kind: 'permission'; id: string; event: PermissionRequestEvent; resolved?: boolean };

interface UseOdinSessionReturn {
  timeline: TimelineEntry[];
  sessionState: SessionState;
  statusMessage: string | null;
  streamError: string | null;
  isLoadingHistory: boolean;
  historyError: string | null;
  wsConnected: boolean;
  hasConversation: boolean;
  sendMessage: (content: string) => void;
  reloadHistory: () => void;
}

/**
 * Full chat session state machine:
 * - loads persisted messages into a unified timeline
 * - connects the WebSocket for the active conversation
 * - accumulates text_chunk streaming into a single assistant message
 * - tracks tool executions by tool_call_id
 * - tracks permission intercepts and their resolution
 */
export function useOdinSession(conversationId: string | null): UseOdinSessionReturn {
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [sessionState, setSessionState] = useState<SessionState>('idle');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const streamBufferRef = useRef<string>('');
  const streamEntryIdRef = useRef<string | null>(null);

  const reloadHistory = useCallback(async () => {
    if (!conversationId) return;
    setIsLoadingHistory(true);
    setHistoryError(null);
    try {
      const msgs = await conversationsApi.getMessages(conversationId);
      setTimeline(
        msgs.map((m) => ({ kind: 'message' as const, id: m.id, message: m }))
      );
      setStreamError(null);
      setStatusMessage(null);
      setSessionState('idle');
      streamBufferRef.current = '';
      streamEntryIdRef.current = null;
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoadingHistory(false);
    }
  }, [conversationId]);

  useEffect(() => {
    if (conversationId) {
      void reloadHistory();
    } else {
      setTimeline([]);
      setSessionState('idle');
      setStatusMessage(null);
      setStreamError(null);
    }
  }, [conversationId, reloadHistory]);

  const handleEvent = useCallback(
    (event: OdinEvent) => {
      switch (event.type) {
        case 'status': {
          setStatusMessage(event.message);
          setSessionState(
            event.message.toLowerCase().includes('waiting') ? 'waiting_auth' : 'thinking'
          );
          break;
        }

        case 'text_chunk': {
          setSessionState('streaming');
          setStatusMessage(null);
          streamBufferRef.current += event.content;
          const content = streamBufferRef.current;

          setTimeline((prev) => {
            const entryId = streamEntryIdRef.current;
            const idx = entryId ? prev.findIndex((e) => e.id === entryId) : -1;
            if (idx >= 0) {
              const entry = prev[idx];
              if (entry.kind === 'message') {
                const next = [...prev];
                next[idx] = {
                  ...entry,
                  message: { ...entry.message, content },
                };
                return next;
              }
            }
            // New streaming assistant entry
            const id = `stream-${Date.now()}`;
            streamEntryIdRef.current = id;
            const msg: Message = {
              id,
              conversation_id: conversationId || '',
              role: 'assistant',
              content,
              tool_name: null,
              tool_call_id: null,
              created_at: new Date().toISOString(),
            };
            return [...prev, { kind: 'message', id, message: msg }];
          });
          break;
        }

        case 'tool_start': {
          setSessionState((s) => (s === 'waiting_auth' ? s : 'thinking'));
          setTimeline((prev) => [
            ...prev,
            {
              kind: 'tool',
              id: `tool-${event.tool_call_id}`,
              execution: {
                toolCallId: event.tool_call_id,
                tool: event.tool,
                arguments: event.arguments,
                status: 'running',
              },
            },
          ]);
          break;
        }

        case 'tool_end': {
          setTimeline((prev) =>
            prev.map((entry) =>
              entry.kind === 'tool' && entry.execution.toolCallId === event.tool_call_id
                ? {
                    ...entry,
                    execution: {
                      ...entry.execution,
                      status: event.success ? 'success' : 'error',
                      result: event.result,
                    },
                  }
                : entry
            )
          );
          break;
        }

        case 'permission_request': {
          setSessionState('waiting_auth');
          setStatusMessage('Waiting for authorization...');
          setTimeline((prev) => [
            ...prev,
            {
              kind: 'permission',
              id: `perm-${event.id}`,
              event,
            },
          ]);
          break;
        }

        case 'permission_resolved': {
          setTimeline((prev) =>
            prev.map((entry) =>
              entry.kind === 'permission' && entry.event.id === event.id
                ? { ...entry, resolved: event.approved }
                : entry
            )
          );
          break;
        }

        case 'done': {
          setSessionState('idle');
          setStatusMessage(null);
          streamBufferRef.current = '';
          streamEntryIdRef.current = null;
          // Intentionally keep the in-memory timeline: tool and permission
          // cards are not persisted by the backend, so reloading here would
          // wipe them. History reload happens on conversation switch/manual refresh.
          break;
        }

        case 'error': {
          setSessionState('error');
          setStreamError(event.message);
          streamBufferRef.current = '';
          streamEntryIdRef.current = null;
          break;
        }

        case 'pong':
          break;
      }
    },
    [conversationId, reloadHistory]
  );

  const { isConnected, sendMessage: wsSend } = useOdinWebSocket({
    conversationId,
    onEvent: handleEvent,
  });

  const sendMessage = useCallback(
    (content: string) => {
      if (!conversationId || !content.trim()) return;
      setStreamError(null);

      const userMsg: Message = {
        id: `local-${Date.now()}`,
        conversation_id: conversationId,
        role: 'user',
        content: content.trim(),
        tool_name: null,
        tool_call_id: null,
        created_at: new Date().toISOString(),
      };

      setTimeline((prev) => [...prev, { kind: 'message', id: userMsg.id, message: userMsg }]);
      streamBufferRef.current = '';
      streamEntryIdRef.current = null;
      setSessionState('thinking');
      setStatusMessage('Thinking...');
      wsSend(content.trim());
    },
    [conversationId, wsSend]
  );

  return {
    timeline,
    sessionState,
    statusMessage,
    streamError,
    isLoadingHistory,
    historyError,
    wsConnected: isConnected,
    hasConversation: conversationId !== null,
    sendMessage,
    reloadHistory,
  };
}
