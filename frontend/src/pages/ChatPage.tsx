import { useState, useRef, useEffect, useCallback, memo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { conversationsApi } from '../api/conversations';
import { permissionsApi } from '../api/permissions';
import { usePolling } from '../hooks/usePolling';
import { useOdinSession, type TimelineEntry } from '../hooks/useOdinSession';
import { ToolExecution } from '../components/ToolExecution';
import { PermissionRequestCard } from '../components/PermissionRequestCard';
import { Button } from '../components/ui/Button';
import { useWsStatus } from '../layouts/ws-status';
import { cn, formatRelativeTime } from '../lib/utils';
import {
  Plus,
  Trash2,
  MessageSquare,
  Loader2,
  AlertTriangle,
  SendHorizonal,
  RefreshCw,
} from 'lucide-react';
import type { Conversation } from '../types/conversation';
import type { PermissionRequest } from '../types/permission';
import type { PermissionRequestEvent } from '../types/websocket';

export function ChatPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const conversationId = searchParams.get('conversation');
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [showSidebar, setShowSidebar] = useState(true);
  const timelineEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const conversations = usePolling<Conversation[]>(
    () => conversationsApi.listConversations(),
    20000
  );

  const session = useOdinSession(conversationId);

  // Publish socket status to the shared context (top bar) — avoids a duplicate socket
  const { setWsConnected } = useWsStatus();
  useEffect(() => {
    setWsConnected(session.wsConnected);
    return () => setWsConnected(false);
  }, [session.wsConnected, setWsConnected]);

  // Select first conversation by default when list loads and nothing selected
  useEffect(() => {
    if (!conversationId && conversations.data && conversations.data.length > 0) {
      setSearchParams(
        { conversation: conversations.data[0].id, title: conversations.data[0].title },
        { replace: true }
      );
    }
  }, [conversationId, conversations.data, setSearchParams]);

  // Auto-scroll on timeline changes (but not when user scrolled up)
  const userScrolledRef = useRef(false);
  useEffect(() => {
    const el = timelineEndRef.current?.parentElement;
    if (el && !userScrolledRef.current) {
      el.scrollTop = el.scrollHeight;
    }
  }, [session.timeline, session.statusMessage]);

  const handleScroll = useCallback(() => {
    const el = timelineEndRef.current?.parentElement;
    if (!el) return;
    userScrolledRef.current = el.scrollHeight - el.scrollTop - el.clientHeight > 80;
  }, []);

  const handleSelectConversation = (conv: Conversation) => {
    setSearchParams({ conversation: conv.id, title: conv.title });
  };

  const handleCreateConversation = async () => {
    try {
      const conv = await conversationsApi.createConversation({});
      conversations.refresh();
      setSearchParams({ conversation: conv.id, title: conv.title });
      textareaRef.current?.focus();
    } catch (err) {
      console.error('Failed to create conversation', err);
    }
  };

  const handleDeleteConversation = async (conv: Conversation) => {
    if (!confirm(`Delete conversation "${conv.title}"?`)) return;
    try {
      await conversationsApi.deleteConversation(conv.id);
      if (conversationId === conv.id) {
        setSearchParams({});
      }
      conversations.refresh();
    } catch (err) {
      console.error('Failed to delete conversation', err);
    }
  };

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!conversationId || !input.trim() || session.sessionState !== 'idle') return;
    setSending(true);
    session.sendMessage(input);
    setInput('');
    setSending(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const activeConv = conversations.data?.find((c) => c.id === conversationId);

  return (
    <div className="flex h-full gap-4 max-w-[1600px] mx-auto">
      {/* Session ledger */}
      <aside
        className={cn(
          'flex-shrink-0 w-72 bg-surface-base border border-subtle rounded-[20px] flex flex-col overflow-hidden',
          !showSidebar && 'hidden md:flex'
        )}
        aria-label="Conversations"
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-subtle">
          <span className="text-xs uppercase tracking-wider text-muted">Sessions</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleCreateConversation}
            aria-label="New conversation"
            title="New conversation"
          >
            <Plus className="w-4 h-4" />
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {conversations.loading && (
            <div className="flex items-center justify-center py-8" role="status" aria-label="Loading conversations">
              <Loader2 className="w-5 h-5 text-accent-primary animate-spin" />
            </div>
          )}
          {conversations.error && (
            <div className="p-4">
              <p className="text-xs text-red-400" role="alert">
                {conversations.error}
              </p>
            </div>
          )}
          {conversations.data && conversations.data.length === 0 && (
            <div className="p-6 text-center">
              <MessageSquare className="w-8 h-8 text-muted mx-auto mb-2" aria-hidden="true" />
              <p className="text-sm text-secondary">No conversations yet</p>
              <button
                onClick={handleCreateConversation}
                className="mt-2 text-xs text-accent-primary hover:text-accent-secondary focus-ring rounded"
              >
                Start the first one
              </button>
            </div>
          )}
          {conversations.data?.map((conv) => {
            const isActive = conv.id === conversationId;
            return (
              <div
                key={conv.id}
                className={cn(
                  'group flex items-center border-b border-subtle/50',
                  isActive ? 'bg-surface-elevated' : 'hover:bg-surface-elevated/50'
                )}
              >
                <button
                  onClick={() => handleSelectConversation(conv)}
                  className={cn(
                    'flex-1 min-w-0 text-left px-4 py-3 transition-colors focus-ring',
                    isActive && 'border-l-2 border-accent-primary'
                  )}
                  aria-current={isActive ? 'true' : undefined}
                >
                  <p className="text-sm text-primary truncate">{conv.title}</p>
                  <p className="text-xs text-muted mt-0.5 font-mono">
                    {formatRelativeTime(conv.updated_at)}
                  </p>
                </button>
                <button
                  onClick={() => handleDeleteConversation(conv)}
                  className="p-2 mr-1 text-muted hover:text-red-400 opacity-0 group-hover:opacity-100 focus-ring rounded transition-opacity"
                  aria-label={`Delete conversation ${conv.title}`}
                  title="Delete"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      </aside>

      {/* Main column */}
      <div className="flex-1 flex flex-col min-w-0 bg-surface-base border border-subtle rounded-[20px] overflow-hidden">
        {/* Session metadata bar */}
        <div className="flex items-center gap-4 px-4 py-2.5 border-b border-subtle bg-surface-container/50">
          <button
            onClick={() => setShowSidebar(!showSidebar)}
            className="md:hidden text-muted hover:text-primary focus-ring rounded"
            aria-label="Toggle sessions panel"
          >
            <MessageSquare className="w-4 h-4" />
          </button>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-primary truncate">
              {activeConv?.title || (conversationId ? 'Conversation' : 'No conversation selected')}
            </p>
            <p className="text-xs text-muted font-mono truncate">
              {conversationId ? `session ${conversationId.slice(0, 8)}` : 'Select or create a session'}
            </p>
          </div>
          <div className="flex items-center gap-3 text-xs font-mono">
            <span className="text-muted hidden sm:inline">WS</span>
            <span className={session.wsConnected ? 'text-green-400' : 'text-red-400'}>
              {session.wsConnected ? 'connected' : 'disconnected'}
            </span>
            {session.sessionState !== 'idle' && (
              <span className="px-2 py-0.5 rounded-full bg-accent-primary/10 text-accent-primary border border-accent-primary/20">
                {session.sessionState.replace('_', ' ')}
              </span>
            )}
          </div>
          <button
            onClick={() => session.reloadHistory()}
            className="text-muted hover:text-primary focus-ring rounded"
            aria-label="Reload conversation history"
            title="Reload history"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Execution timeline */}
        <div
          className="flex-1 overflow-y-auto scrollbar-thin px-4 md:px-8 py-6"
          onScroll={handleScroll}
          role="log"
          aria-label="Execution timeline"
          aria-live="polite"
        >
          {!conversationId && (
            <div className="h-full flex flex-col items-center justify-center text-center">
              <MessageSquare className="w-10 h-10 text-muted mb-3" aria-hidden="true" />
              <p className="text-secondary">Select a session or create a new one</p>
              <p className="text-muted text-sm mt-1">Conversations persist in the ODIN database</p>
            </div>
          )}

          {conversationId && session.isLoadingHistory && (
            <div className="flex items-center justify-center py-12" role="status">
              <Loader2 className="w-5 h-5 text-accent-primary animate-spin" />
            </div>
          )}

          {conversationId && session.historyError && (
            <div className="my-4 p-4 rounded-xl bg-red-400/10 border border-red-400/20" role="alert">
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-sm text-red-400 font-medium">Failed to load messages</p>
                  <p className="text-xs text-red-400/70 font-mono mt-1">{session.historyError}</p>
                  <button
                    onClick={() => session.reloadHistory()}
                    className="mt-2 text-xs text-accent-primary hover:text-accent-secondary focus-ring rounded"
                  >
                    Retry
                  </button>
                </div>
              </div>
            </div>
          )}

          {conversationId && !session.isLoadingHistory && session.timeline.length === 0 && !session.historyError && (
            <div className="h-full flex flex-col items-center justify-center text-center">
              <p className="text-secondary">Empty session</p>
              <p className="text-muted text-sm mt-1">
                Send a message to start working with ODIN
              </p>
            </div>
          )}

          <div className="space-y-4 max-w-4xl mx-auto">
            {session.timeline.map((entry) => (
              <TimelineEntryView key={entry.id} entry={entry} />
            ))}

            {/* Status indicator */}
            {session.sessionState !== 'idle' && session.statusMessage && (
              <div className="flex items-center gap-2 text-sm text-secondary py-1" role="status">
                <Loader2 className="w-3.5 h-3.5 text-accent-primary animate-spin" aria-hidden="true" />
                <span className="font-mono">{session.statusMessage}</span>
              </div>
            )}

            {/* Explicit error display */}
            {session.streamError && (
              <div
                className="p-4 rounded-xl bg-red-400/10 border border-red-400/20"
                role="alert"
              >
                <div className="flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-sm text-red-400 font-medium">Agent error</p>
                    <p className="text-xs text-red-400/80 font-mono mt-1 break-words">
                      {session.streamError}
                    </p>
                  </div>
                </div>
              </div>
            )}

            <div ref={timelineEndRef} />
          </div>
        </div>

        {/* Command input */}
        <form
          onSubmit={handleSubmit}
          className="border-t border-subtle p-4 bg-surface-container/50"
          aria-label="Command input"
        >
          <div className="max-w-4xl mx-auto">
            <div className="flex items-end gap-3 bg-surface-elevated border border-subtle rounded-xl px-4 py-3 focus-within:border-accent-primary/40 transition-colors">
              <span className="text-accent-primary font-mono text-sm select-none" aria-hidden="true">
                ›
              </span>
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  !conversationId
                    ? 'Select a session to start...'
                    : session.sessionState !== 'idle'
                      ? 'ODIN is working...'
                      : 'Message ODIN...'
                }
                disabled={!conversationId || session.sessionState !== 'idle'}
                rows={2}
                className="flex-1 bg-transparent text-sm text-primary placeholder-muted resize-none focus:outline-none min-h-[40px] max-h-32 font-mono disabled:cursor-not-allowed disabled:opacity-60"
                aria-label="Message ODIN"
              />
              <Button
                type="submit"
                size="sm"
                disabled={!conversationId || !input.trim() || session.sessionState !== 'idle'}
                loading={sending}
                aria-label="Send message"
              >
                <SendHorizonal className="w-4 h-4" />
              </Button>
            </div>
            <p className="text-xs text-muted mt-1.5 font-mono">
              Enter to send · Shift+Enter for newline
              {conversationId && !session.wsConnected && (
                <span className="text-red-400"> · WebSocket disconnected</span>
              )}
            </p>
          </div>
        </form>
      </div>
    </div>
  );
}

/** Renders a single timeline entry by kind. Memoized so text_chunk updates don't re-render everything. */
const TimelineEntryView = memo(function TimelineEntryView({ entry }: { entry: TimelineEntry }) {
  switch (entry.kind) {
    case 'message':
      return <MessageView message={entry.message} />;
    case 'tool':
      return <ToolExecution execution={entry.execution} />;
    case 'permission':
      return <TimelinePermission event={entry.event} resolved={entry.resolved} />;
  }
});

const MessageView = memo(function MessageView({ message }: { message: { role: string; content: string; created_at: string } }) {
  const isUser = message.role === 'user';

  if (message.role === 'tool') {
    return (
      <div className="font-mono text-xs text-muted bg-surface-container rounded-lg px-3 py-2 border border-subtle break-all">
        {message.content.slice(0, 500)}
      </div>
    );
  }

  if (message.role === 'system') {
    return (
      <p className="text-xs text-muted font-mono text-center py-1">{message.content}</p>
    );
  }

  return (
    <article className={cn('group relative pl-4', isUser ? 'border-l-2 border-accent-primary' : 'border-l-2 border-accent-subtle/40')}>
      <header className="flex items-center gap-2 mb-1.5">
        <span
          className={cn(
            'text-xs font-medium uppercase tracking-wider',
            isUser ? 'text-accent-primary' : 'text-accent-subtle'
          )}
        >
          {isUser ? 'Operator' : 'ODIN'}
        </span>
        <span className="text-xs text-muted font-mono opacity-0 group-hover:opacity-100 transition-opacity">
          {new Date(message.created_at).toLocaleTimeString()}
        </span>
      </header>
      <div
        className={cn(
          'whitespace-pre-wrap break-words text-sm leading-relaxed',
          isUser ? 'text-primary' : 'text-secondary'
        )}
      >
        {message.content || (
          <span className="text-muted italic font-mono text-xs">streaming…</span>
        )}
      </div>
    </article>
  );
});

function TimelinePermission({
  event,
  resolved,
}: {
  event: PermissionRequestEvent;
  resolved?: boolean;
}) {
  const [permission, setPermission] = useState<PermissionRequest | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    // WS event carries the intercept data; fetch full record for arguments_json + timestamps
    let cancelled = false;
    permissionsApi
      .listPermissions(undefined, 200)
      .then((list) => {
        if (cancelled) return;
        const found = list.find((p) => p.id === event.id);
        if (found) setPermission(found);
        else
          setPermission({
            id: event.id,
            conversation_id: '',
            tool: event.tool,
            operation: event.operation,
            arguments_json: JSON.stringify(event.arguments),
            target: event.target,
            reason: event.reason,
            risk_level: event.risk_level as PermissionRequest['risk_level'],
            status: resolved === undefined ? 'pending' : resolved ? 'approved' : 'denied',
            created_at: new Date().toISOString(),
            resolved_at: null,
          });
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [event, resolved]);

  if (loadError) {
    return (
      <div className="p-3 rounded-xl bg-red-400/10 border border-red-400/20 text-xs text-red-400 font-mono" role="alert">
        Permission {event.id.slice(0, 8)}: {loadError}
      </div>
    );
  }

  if (!permission) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted font-mono py-2" role="status">
        <Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" />
        Loading permission request…
      </div>
    );
  }

  return (
    <PermissionRequestCard
      permission={{
        ...permission,
        status: resolved === undefined ? 'pending' : resolved ? 'approved' : 'denied',
      }}
    />
  );
}
