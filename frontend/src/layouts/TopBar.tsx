import { useEffect, useState } from 'react';
import { cn } from '../lib/utils';
import { Button } from '../components/ui/Button';

interface TopBarProps {
  onMenuClick: () => void;
  healthData?: {
    status: string;
    model: string;
    model_provider: string;
    tools_count: number;
    agent_ready: boolean;
    version?: string;
  };
  wsConnected: boolean;
  activeConversationTitle?: string;
}

export function TopBar({
  onMenuClick,
  healthData,
  wsConnected,
  activeConversationTitle,
}: TopBarProps) {
  const [time, setTime] = useState(new Date().toLocaleTimeString('en-US', { 
    hour12: false, 
    timeZone: 'UTC',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }));

  useEffect(() => {
    const interval = setInterval(() => {
      setTime(new Date().toLocaleTimeString('en-US', { 
        hour12: false, 
        timeZone: 'UTC',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const isOnline = healthData?.status === 'online' && healthData?.agent_ready;

  return (
    <header className="sticky top-0 z-30 h-14 bg-surface-base/80 backdrop-blur-sm border-b border-subtle flex items-center justify-between px-4">
      {/* Left: Menu button + Connection status */}
      <div className="flex items-center gap-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={onMenuClick}
          aria-label="Toggle navigation menu"
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        </Button>

        <div className="flex items-center gap-2 hidden sm:flex">
          <span className={cn(
            'w-2 h-2 rounded-full',
            isOnline ? 'bg-green-400' : 'bg-red-400'
          )} aria-hidden="true" />
          <span className={cn(
            'text-xs font-medium',
            isOnline ? 'text-green-400' : 'text-red-400'
          )}>
            {isOnline ? 'ONLINE' : 'OFFLINE'}
          </span>
        </div>
      </div>

      {/* Center: Active conversation / Runtime info */}
      <div className="flex-1 flex items-center justify-center gap-6 max-w-3xl">
        {activeConversationTitle && (
          <div className="text-center">
            <p className="text-sm font-medium text-primary truncate max-w-xs" title={activeConversationTitle}>
              {activeConversationTitle}
            </p>
            <p className="text-xs text-muted font-mono">Active session</p>
          </div>
        )}

        {healthData && (
          <div className="hidden md:flex items-center gap-4 text-xs text-secondary">
            <div className="flex items-center gap-1">
              <span className="text-muted">Provider:</span>
              <span className="font-mono text-primary">{healthData.model_provider}</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-muted">Model:</span>
              <span className="font-mono text-primary">{healthData.model}</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-muted">Tools:</span>
              <span className="font-mono text-primary">{healthData.tools_count}</span>
            </div>
            <div className="flex items-center gap-1">
              <span className="text-muted">WS:</span>
              <span className={cn('font-mono', wsConnected ? 'text-green-400' : 'text-red-400')}>
                {wsConnected ? 'Connected' : 'Disconnected'}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Right: UTC Clock */}
      <div className="flex items-center gap-3">
        <div className="hidden sm:flex items-center gap-1.5 text-xs font-mono text-muted">
          <span className="text-accent-subtle">UTC</span>
          <span className="text-primary tabular-nums">{time}</span>
        </div>
      </div>
    </header>
  );
}