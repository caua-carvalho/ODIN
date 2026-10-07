import { useState, memo } from 'react';
import { cn } from '../lib/utils';
import { CheckCircle, XCircle, Loader2, ChevronDown, ChevronRight } from 'lucide-react';

export interface ToolExecutionData {
  toolCallId: string;
  tool: string;
  arguments: Record<string, unknown>;
  status: 'running' | 'success' | 'error';
  result?: Record<string, unknown>;
}

interface ToolExecutionProps {
  execution: ToolExecutionData;
}

/**
 * Timeline item for a tool execution.
 * No duration is shown — the backend does not provide one.
 */
export const ToolExecution = memo(function ToolExecution({ execution }: ToolExecutionProps) {
  const [expanded, setExpanded] = useState(execution.status === 'running');
  const { tool, arguments: args, status, result, toolCallId } = execution;

  const statusConfig = {
    running: {
      icon: Loader2,
      iconClass: 'text-accent-subtle animate-spin',
      label: 'RUNNING',
      labelClass: 'text-accent-subtle',
      border: 'border-accent-subtle/30',
    },
    success: {
      icon: CheckCircle,
      iconClass: 'text-green-400',
      label: 'SUCCESS',
      labelClass: 'text-green-400',
      border: 'border-green-400/20',
    },
    error: {
      icon: XCircle,
      iconClass: 'text-red-400',
      label: 'ERROR',
      labelClass: 'text-red-400',
      border: 'border-red-400/30',
    },
  } as const;

  const cfg = statusConfig[status];
  const StatusIcon = cfg.icon;

  const output = result?.output;
  const error = result?.error;

  return (
    <div className={cn('rounded-xl border bg-surface-container overflow-hidden', cfg.border)}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-surface-elevated/50 transition-colors focus-ring"
        aria-expanded={expanded}
        aria-label={`Tool execution ${tool} — ${cfg.label}`}
      >
        <StatusIcon className={cn('w-4 h-4 flex-shrink-0', cfg.iconClass)} />
        <span className="font-mono text-sm text-primary truncate">
          {tool}
        </span>
        <span className="hidden sm:inline text-xs font-mono text-muted truncate">
          #{toolCallId.slice(0, 8)}
        </span>
        <div className="ml-auto flex items-center gap-2 flex-shrink-0">
          <span className={cn('text-xs font-medium tracking-wider', cfg.labelClass)}>
            {cfg.label}
          </span>
          {expanded ? (
            <ChevronDown className="w-4 h-4 text-muted" />
          ) : (
            <ChevronRight className="w-4 h-4 text-muted" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-subtle pt-3">
          {/* Arguments */}
          <div>
            <p className="text-xs uppercase tracking-wider text-muted mb-1.5">Arguments</p>
            <pre className="font-mono text-xs text-secondary bg-surface-elevated rounded-lg p-3 overflow-x-auto scrollbar-thin whitespace-pre-wrap break-all max-h-40 overflow-y-auto">
              {JSON.stringify(args, null, 2)}
            </pre>
          </div>

          {/* Error */}
          {typeof error === 'string' && error && (
            <div>
              <p className="text-xs uppercase tracking-wider text-red-400 mb-1.5">Error</p>
              <pre className="font-mono text-xs text-red-400 bg-red-400/5 border border-red-400/20 rounded-lg p-3 overflow-x-auto scrollbar-thin whitespace-pre-wrap break-all">
                {error}
              </pre>
            </div>
          )}

          {/* Output */}
          {output !== undefined && output !== null && status !== 'running' && (
            <div>
              <p className="text-xs uppercase tracking-wider text-muted mb-1.5">Output</p>
              <pre className="font-mono text-xs text-secondary bg-surface-elevated rounded-lg p-3 overflow-x-auto scrollbar-thin whitespace-pre-wrap break-all max-h-64 overflow-y-auto">
                {typeof output === 'string' ? output : JSON.stringify(output, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
});
