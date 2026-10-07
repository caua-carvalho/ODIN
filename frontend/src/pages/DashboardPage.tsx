import { useMemo, useCallback } from 'react';
import { usePolling } from '../hooks/usePolling';
import { healthApi } from '../api/health';
import { systemApi } from '../api/system';
import { permissionsApi } from '../api/permissions';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { PermissionRequestCard } from '../components/PermissionRequestCard';
import { cn, formatBytes, formatUptime } from '../lib/utils';
import { Cpu, HardDrive, MemoryStick, Activity, AlertTriangle, CheckCircle, XCircle, RefreshCw } from 'lucide-react';
import type { HealthResponse } from '../types/health';
import type { SystemInfo } from '../types/system';
import type { PermissionRequest } from '../types/permission';

export function DashboardPage() {
  const health = usePolling<HealthResponse>(() => healthApi.getHealth(), 15000);
  const system = usePolling<SystemInfo>(() => systemApi.getSystemInfo(), 5000);
  const pending = usePolling<PermissionRequest[]>(() => permissionsApi.listPendingPermissions(), 10000);

  const allLoading = health.loading && system.loading && pending.loading;
  const offline = health.error !== null && health.data === null;

  const handlePermissionResolved = useCallback(() => {
    pending.refresh();
    health.refresh();
  }, [pending, health]);

  const criticalPerms = useMemo(
    () => (pending.data || []).filter((p) => p.risk_level === 'critical' || p.risk_level === 'high'),
    [pending.data]
  );
  const otherPerms = useMemo(
    () => (pending.data || []).filter((p) => p.risk_level !== 'critical' && p.risk_level !== 'high'),
    [pending.data]
  );

  if (allLoading) {
    return (
      <div className="flex items-center justify-center h-64" role="status" aria-label="Loading dashboard">
        <RefreshCw className="w-6 h-6 text-accent-primary animate-spin" />
      </div>
    );
  }

  if (offline) {
    return (
      <div className="flex items-center justify-center h-64 text-center">
        <div>
          <XCircle className="w-12 h-12 text-red-400 mx-auto mb-4" aria-hidden="true" />
          <h2 className="text-xl font-semibold text-primary mb-2">OFFLINE</h2>
          <p className="text-secondary">Unable to connect to ODIN runtime</p>
          <p className="text-muted text-sm mt-1 font-mono">{health.error}</p>
          <button
            onClick={() => {
              health.refresh();
              system.refresh();
              pending.refresh();
            }}
            className="mt-4 px-4 py-2 bg-accent-primary text-white rounded-xl text-sm font-medium hover:bg-accent-secondary transition-colors focus-ring"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const h = health.data;
  const s = system.data;
  const isReady = h?.status === 'online' && h?.agent_ready;

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-primary tracking-tight">Command Dashboard</h1>
          <p className="text-secondary mt-1">Runtime status, system telemetry and pending authorizations</p>
        </div>
        <span
          className={cn(
            'px-3 py-1 rounded-full text-xs font-medium border',
            isReady
              ? 'bg-green-400/10 text-green-400 border-green-400/20'
              : 'bg-red-400/10 text-red-400 border-red-400/20'
          )}
        >
          {isReady ? 'READY' : 'OFFLINE'}
        </span>
      </div>

      {/* ODIN Core */}
      <Card variant="elevated" className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-accent-primary/[0.04] via-transparent to-accent-subtle/[0.03] pointer-events-none" />
        <CardContent className="relative py-8">
          <div className="flex flex-col items-center text-center space-y-4">
            <div className="relative w-48 h-48 flex items-center justify-center">
              {/* Concentric orbital rings (decorative) */}
              <div
                className="absolute w-36 h-36 rounded-full border border-white/[0.06] animate-pulse-subtle pointer-events-none"
                aria-hidden="true"
              />
              <div
                className="absolute w-[11.5rem] h-[11.5rem] rounded-full border border-accent-primary/10 pointer-events-none"
                aria-hidden="true"
              />
              <div className="relative w-24 h-24 rounded-2xl bg-surface-container border border-accent-primary/30 flex items-center justify-center shadow-[0_0_48px_rgba(255,122,0,0.12)]">
                <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-accent-primary" aria-hidden="true">
                  <path d="M12 2L2 7l10 5 10-5-10-5z" strokeLinejoin="round" />
                  <path d="M2 17l10 5 10-5" strokeLinejoin="round" />
                  <path d="M2 12l10 5 10-5" strokeLinejoin="round" />
                </svg>
              </div>
              {isReady && (
                <div className="absolute top-6 right-10 w-4 h-4 bg-green-400 rounded-full border-2 border-surface-base animate-pulse-subtle" aria-hidden="true" />
              )}
            </div>

            <div className="space-y-1">
              <h2 className="text-xl font-semibold text-primary">
                {isReady ? 'Online · Ready' : 'Unavailable'}
              </h2>
              <p className="text-secondary font-mono text-sm">
                {h ? `${h.model_provider} · ${h.model}` : 'No runtime data'}
              </p>
              {h && (
                <p className="text-muted font-mono text-xs break-all">workspace: {h.workspace}</p>
              )}
            </div>

            <div className="flex items-center justify-center gap-6 pt-4 border-t border-subtle w-full max-w-md">
              <div className="text-center">
                <p className="text-2xl font-bold text-primary tabular-nums">{h?.tools_count ?? '—'}</p>
                <p className="text-xs text-muted">Tools</p>
              </div>
              <div className="w-px h-8 bg-border-subtle" aria-hidden="true" />
              <div className="text-center">
                <p className="text-2xl font-bold text-primary tabular-nums">
                  {s ? `${s.cpu_percent.toFixed(0)}%` : '—'}
                </p>
                <p className="text-xs text-muted">CPU</p>
              </div>
              <div className="w-px h-8 bg-border-subtle" aria-hidden="true" />
              <div className="text-center">
                <p className="text-2xl font-bold text-primary tabular-nums">
                  {s ? `${s.memory_percent.toFixed(0)}%` : '—'}
                </p>
                <p className="text-xs text-muted">Memory</p>
              </div>
              <div className="w-px h-8 bg-border-subtle" aria-hidden="true" />
              <div className="text-center">
                <p className="text-2xl font-bold text-primary tabular-nums">
                  {pending.data ? pending.data.length : '—'}
                </p>
                <p className="text-xs text-muted">Pending</p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          icon={Cpu}
          iconClass="text-blue-400"
          label="CPU"
          value={s ? `${s.cpu_percent.toFixed(1)}%` : '—'}
          detail={s ? `load ${s.load_avg.map((n) => n.toFixed(2)).join(' · ')}` : 'Unavailable'}
        />
        <MetricCard
          icon={MemoryStick}
          iconClass="text-green-400"
          label="Memory"
          value={s ? formatBytes(s.memory_used) : '—'}
          detail={s ? `${s.memory_percent.toFixed(1)}% of ${formatBytes(s.memory_total)}` : 'Unavailable'}
          percent={s?.memory_percent}
        />
        <MetricCard
          icon={HardDrive}
          iconClass="text-amber-400"
          label="Disk"
          value={s ? formatBytes(s.disk_used) : '—'}
          detail={s ? `${s.disk_percent.toFixed(1)}% of ${formatBytes(s.disk_total)}` : 'Unavailable'}
          percent={s?.disk_percent}
        />
        <MetricCard
          icon={Activity}
          iconClass="text-purple-400"
          label="Uptime"
          value={s ? formatUptime(s.uptime_seconds) : '—'}
          detail="ODIN runtime uptime"
        />
      </div>

      {/* Pending authorizations + status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card variant="container" className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="w-4 h-4 text-accent-primary" aria-hidden="true" />
              Pending Authorizations
            </CardTitle>
            <span className="text-xs text-muted font-mono">
              {pending.data ? `${pending.data.length} pending` : '—'}
            </span>
          </CardHeader>
          <CardContent className="py-4 space-y-3">
            {pending.error && (
              <p className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-3 py-2" role="alert">
                Failed to load permissions: {pending.error}
              </p>
            )}
            {!pending.data && !pending.error && (
              <p className="text-sm text-muted py-4 text-center">Loading pending authorizations…</p>
            )}
            {pending.data && pending.data.length === 0 && (
              <div className="py-6 text-center">
                <CheckCircle className="w-10 h-10 text-green-400 mx-auto mb-3" aria-hidden="true" />
                <p className="text-secondary">No pending permissions</p>
                <p className="text-muted text-sm mt-1">Nothing is waiting for your authorization</p>
              </div>
            )}
            {pending.data && pending.data.length > 0 && (
              <div className="space-y-3 max-h-[480px] overflow-y-auto scrollbar-thin pr-1">
                {criticalPerms.map((perm) => (
                  <PermissionRequestCard key={perm.id} permission={perm} compact onResolved={handlePermissionResolved} />
                ))}
                {otherPerms.map((perm) => (
                  <PermissionRequestCard key={perm.id} permission={perm} compact onResolved={handlePermissionResolved} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card variant="container">
          <CardHeader>
            <CardTitle className="text-base">Runtime</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <StatusRow label="Runtime" value={h?.status === 'online' ? 'online' : 'offline'} ok={h?.status === 'online'} />
            <StatusRow label="Agent" value={h?.agent_ready ? 'ready' : 'not ready'} ok={!!h?.agent_ready} />
            <StatusRow label="Provider" value={h?.model_provider ?? '—'} ok={!!h?.model_provider} mono />
            <StatusRow label="Model" value={h?.model ?? '—'} ok={!!h?.model} mono />
            <StatusRow label="Tools" value={h ? `${h.tools_count} registered` : '—'} ok={!!h} mono />
            <StatusRow label="Version" value={h?.version ?? '—'} ok mono />
            <div className="pt-2 border-t border-subtle">
              <p className="text-xs uppercase tracking-wider text-muted mb-1">Workspace</p>
              <p className="font-mono text-xs text-accent-subtle break-all">{h?.workspace ?? '—'}</p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function MetricCard({
  icon: Icon,
  iconClass,
  label,
  value,
  detail,
  percent,
}: {
  icon: typeof Cpu;
  iconClass: string;
  label: string;
  value: string;
  detail: string;
  percent?: number;
}) {
  return (
    <Card variant="container">
      <CardContent className="py-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-surface-elevated rounded-xl">
            <Icon className={cn('w-5 h-5', iconClass)} aria-hidden="true" />
          </div>
          <div className="min-w-0">
            <p className="text-xs text-muted">{label}</p>
            <p className="font-mono text-sm text-primary tabular-nums truncate">{value}</p>
          </div>
        </div>
        {percent !== undefined && (
          <div className="mt-3 h-1 rounded-full bg-surface-elevated overflow-hidden" aria-hidden="true">
            <div
              className={cn('h-full rounded-full', percent > 85 ? 'bg-red-400' : 'bg-accent-primary')}
              style={{ width: `${Math.min(percent, 100)}%` }}
            />
          </div>
        )}
        <p className="text-xs text-muted mt-2 font-mono truncate">{detail}</p>
      </CardContent>
    </Card>
  );
}

function StatusRow({ label, value, ok, mono }: { label: string; value: string; ok: boolean; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-secondary">{label}</span>
      <div className="flex items-center gap-2 min-w-0">
        <span className={cn('text-primary truncate', mono ? 'font-mono text-xs' : 'text-sm')}>{value}</span>
        <span
          className={cn('w-2 h-2 rounded-full flex-shrink-0', ok ? 'bg-green-400' : 'bg-red-400')}
          aria-hidden="true"
        />
      </div>
    </div>
  );
}
