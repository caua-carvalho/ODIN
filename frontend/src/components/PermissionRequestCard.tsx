import { useState } from 'react';
import { cn, formatRelativeTime, getStatusColor } from '../lib/utils';
import { Badge } from './ui/Badge';
import { ShieldAlert, Check, X, Loader2 } from 'lucide-react';
import { permissionsApi } from '../api/permissions';
import type { PermissionRequest as PermissionRequestType } from '../types/permission';

interface PermissionRequestCardProps {
  permission: PermissionRequestType;
  onResolved?: () => void;
  compact?: boolean;
}

/**
 * Reusable permission intercept component.
 * Used in chat timeline, dashboard and permissions page.
 * The frontend only requests approve/deny — the backend is the security authority.
 */
export function PermissionRequestCard({
  permission,
  onResolved,
  compact = false,
}: PermissionRequestCardProps) {
  const [actionLoading, setActionLoading] = useState<'approve' | 'deny' | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const isPending = permission.status === 'pending';

  const handleAction = async (action: 'approve' | 'deny') => {
    if (!isPending || actionLoading) return;
    setActionLoading(action);
    setActionError(null);
    try {
      if (action === 'approve') {
        await permissionsApi.approvePermission(permission.id);
      } else {
        await permissionsApi.denyPermission(permission.id);
      }
      onResolved?.();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : `Failed to ${action}`);
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div
      className={cn(
        'rounded-xl border bg-surface-container',
        isPending ? 'border-accent-primary/40 shadow-[0_0_24px_rgba(255,122,0,0.08)]' : 'border-subtle'
      )}
      role="region"
      aria-label={`Permission request for ${permission.tool}`}
    >
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-subtle">
        <ShieldAlert className={cn('w-4 h-4', isPending ? 'text-accent-primary' : 'text-muted')} />
        <span className="text-xs font-medium uppercase tracking-wider text-secondary">
          Permission Intercept
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          <Badge variant="risk" value={permission.risk_level}>
            {permission.risk_level}
          </Badge>
          <Badge variant="status" value={permission.status}>
            {permission.status}
          </Badge>
        </div>
      </div>

      <div className="px-4 py-3 space-y-2">
        <div className="grid grid-cols-1 sm:grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
          <span className="text-muted text-xs uppercase tracking-wider pt-0.5">Tool</span>
          <span className="font-mono text-primary break-all">{permission.tool}</span>

          <span className="text-muted text-xs uppercase tracking-wider pt-0.5">Operation</span>
          <span className="font-mono text-primary">{permission.operation}</span>

          <span className="text-muted text-xs uppercase tracking-wider pt-0.5">Target</span>
          <span className="font-mono text-accent-subtle break-all">{permission.target}</span>

          {permission.reason && (
            <>
              <span className="text-muted text-xs uppercase tracking-wider pt-0.5">Reason</span>
              <span className="text-secondary break-words">{permission.reason}</span>
            </>
          )}

          {!compact && (
            <>
              <span className="text-muted text-xs uppercase tracking-wider pt-0.5">Arguments</span>
              <pre className="font-mono text-xs text-secondary bg-surface-elevated rounded-lg p-2 overflow-x-auto max-h-32 overflow-y-auto scrollbar-thin whitespace-pre-wrap break-all">
                {permission.arguments_json}
              </pre>
            </>
          )}

          {!compact && (
            <>
              <span className="text-muted text-xs uppercase tracking-wider pt-0.5">Requested</span>
              <span className="text-muted text-xs font-mono">
                {formatRelativeTime(permission.created_at)}
              </span>
            </>
          )}
        </div>

        {actionError && (
          <p className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-3 py-2" role="alert">
            {actionError}
          </p>
        )}

        {isPending && (
          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              onClick={() => handleAction('deny')}
              disabled={actionLoading !== null}
              className={cn(
                'inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium transition-colors focus-ring',
                'bg-red-600 text-white hover:bg-red-500',
                actionLoading && 'opacity-50 cursor-not-allowed'
              )}
              aria-label={`Deny permission for ${permission.tool}`}
            >
              {actionLoading === 'deny' ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <X className="w-4 h-4" />
              )}
              DENY
            </button>
            <button
              onClick={() => handleAction('approve')}
              disabled={actionLoading !== null}
              className={cn(
                'inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium transition-colors focus-ring',
                'bg-green-600 text-white hover:bg-green-500',
                actionLoading && 'opacity-50 cursor-not-allowed'
              )}
              aria-label={`Approve permission for ${permission.tool}`}
            >
              {actionLoading === 'approve' ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Check className="w-4 h-4" />
              )}
              APPROVE
            </button>
          </div>
        )}

        {!isPending && permission.resolved_at && (
          <p className={cn('text-xs font-mono text-right', getStatusColor(permission.status).split(' ')[0])}>
            {permission.status} · {formatRelativeTime(permission.resolved_at)}
          </p>
        )}
      </div>
    </div>
  );
}
