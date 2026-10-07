import { useState, useMemo } from 'react';
import { usePolling } from '../hooks/usePolling';
import { permissionsApi } from '../api/permissions';
import { healthApi } from '../api/health';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { PermissionRequestCard } from '../components/PermissionRequestCard';
import { Input } from '../components/ui/Input';
import { cn, formatRelativeTime } from '../lib/utils';
import { Loader2, AlertTriangle, Shield, CheckCircle, Clock, Search, Lock } from 'lucide-react';
import type { PermissionRequest, PermissionStatus } from '../types/permission';
import type { HealthResponse } from '../types/health';

type StatusFilter = 'all' | PermissionStatus;

const STATUS_TABS: { id: StatusFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'pending', label: 'Pending' },
  { id: 'approved', label: 'Approved' },
  { id: 'denied', label: 'Denied' },
  { id: 'expired', label: 'Expired' },
];

export function PermissionsPage() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [search, setSearch] = useState('');

  const allPermissions = usePolling<PermissionRequest[]>(
    () => permissionsApi.listPermissions(undefined, 200),
    8000
  );
  const pendingPermissions = usePolling<PermissionRequest[]>(
    () => permissionsApi.listPendingPermissions(),
    8000
  );
  const health = usePolling<HealthResponse>(() => healthApi.getHealth(), 30000);

  const filtered = useMemo(() => {
    const list = allPermissions.data ?? [];
    const byStatus = statusFilter === 'all' ? list : list.filter((p) => p.status === statusFilter);
    const q = search.trim().toLowerCase();
    if (!q) return byStatus;
    return byStatus.filter((p) =>
      [p.tool, p.operation, p.target, p.status, p.risk_level, p.reason ?? '', p.conversation_id]
        .join(' ')
        .toLowerCase()
        .includes(q)
    );
  }, [allPermissions.data, statusFilter, search]);

  const counts = useMemo(() => {
    const list = allPermissions.data ?? [];
    return {
      all: list.length,
      pending: list.filter((p) => p.status === 'pending').length,
      approved: list.filter((p) => p.status === 'approved').length,
      denied: list.filter((p) => p.status === 'denied').length,
      expired: list.filter((p) => p.status === 'expired').length,
    };
  }, [allPermissions.data]);

  const stats = useMemo(() => {
    const list = allPermissions.data ?? [];
    const approved = list.filter((p) => p.status === 'approved').length;
    const denied = list.filter((p) => p.status === 'denied').length;
    const resolved = approved + denied;
    return { approved, denied, resolved };
  }, [allPermissions.data]);

  const handleResolved = () => {
    allPermissions.refresh();
    pendingPermissions.refresh();
  };

  if (allPermissions.loading && !allPermissions.data) {
    return (
      <div className="flex items-center justify-center h-64" role="status" aria-label="Loading permissions">
        <Loader2 className="w-6 h-6 text-accent-primary animate-spin" />
      </div>
    );
  }

  if (allPermissions.error && !allPermissions.data) {
    return (
      <div className="flex items-center justify-center h-64 text-center">
        <div>
          <AlertTriangle className="w-10 h-10 text-accent-secondary mx-auto mb-3" aria-hidden="true" />
          <h2 className="text-lg font-semibold text-primary">Failed to load permissions</h2>
          <p className="text-sm text-secondary mt-1 font-mono">{allPermissions.error}</p>
          <button
            onClick={allPermissions.refresh}
            className="mt-4 px-4 py-2 bg-accent-primary text-white rounded-xl text-sm hover:bg-accent-secondary transition-colors focus-ring"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const pendingList = pendingPermissions.data ?? [];

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-primary tracking-tight">Security Console</h1>
          <p className="text-secondary mt-1">
            Human-in-the-loop authorization requests · backend is the security authority
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs font-mono">
          <span className="px-2 py-1 bg-accent-primary/10 text-accent-primary border border-accent-primary/20 rounded-lg">
            {counts.pending} pending
          </span>
          <span className="px-2 py-1 bg-green-400/10 text-green-400 border border-green-400/20 rounded-lg">
            {counts.approved} approved
          </span>
          <span className="px-2 py-1 bg-red-400/10 text-red-400 border border-red-400/20 rounded-lg">
            {counts.denied} denied
          </span>
        </div>
      </div>

      {/* Security posture overview (§4.4) — all values from the backend */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card variant="container">
          <CardContent className="py-5">
            <div className="flex items-center gap-2 mb-2">
              <Lock className="w-4 h-4 text-accent-subtle" aria-hidden="true" />
              <p className="text-xs uppercase tracking-wider text-muted">Security Posture</p>
            </div>
            <p className="text-sm font-medium text-primary">Workspace boundary + HITL approval</p>
            <p className="text-xs text-secondary mt-1.5 font-mono break-all">
              {health.data?.workspace ?? '—'}
            </p>
          </CardContent>
        </Card>

        <Card variant="container">
          <CardContent className="py-5">
            <div className="flex items-center gap-2 mb-2">
              <Shield className="w-4 h-4 text-accent-primary" aria-hidden="true" />
              <p className="text-xs uppercase tracking-wider text-muted">Pending Decisions</p>
            </div>
            <p className="font-mono text-3xl font-bold text-primary tabular-nums">
              {pendingList.length}
            </p>
            <p className="text-xs text-secondary mt-1">
              {pendingList.length === 0 ? 'Queue is clear' : 'Awaiting your sign-off'}
            </p>
          </CardContent>
        </Card>

        <Card variant="container">
          <CardContent className="py-5">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle className="w-4 h-4 text-green-400" aria-hidden="true" />
              <p className="text-xs uppercase tracking-wider text-muted">Authorizations Ratio</p>
            </div>
            <p className="font-mono text-lg font-bold text-primary tabular-nums">
              {String(stats.approved).padStart(2, '0')} approved
              <span className="text-muted font-normal"> / </span>
              {String(stats.denied).padStart(2, '0')} denied
            </p>
            <div
              className="mt-2 h-1.5 rounded-full bg-surface-elevated overflow-hidden flex"
              role="progressbar"
              aria-valuenow={stats.approved}
              aria-valuemin={0}
              aria-valuemax={Math.max(stats.resolved, 1)}
              aria-label="Approved versus denied ratio"
            >
              <div
                className="h-full bg-green-400 transition-all duration-500"
                style={{
                  width: stats.resolved > 0 ? `${(stats.approved / stats.resolved) * 100}%` : '0%',
                }}
              />
              <div
                className="h-full bg-red-400 transition-all duration-500"
                style={{
                  width: stats.resolved > 0 ? `${(stats.denied / stats.resolved) * 100}%` : '0%',
                }}
              />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Pending queue */}
      <Card variant="container">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <Shield className="w-4 h-4 text-accent-primary" aria-hidden="true" />
            Pending Decisions
          </CardTitle>
          <span className="text-xs text-muted font-mono">{pendingList.length} waiting</span>
        </CardHeader>
        <CardContent className="py-4 space-y-3">
          {pendingPermissions.error && (
            <p className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-3 py-2" role="alert">
              {pendingPermissions.error}
            </p>
          )}
          {!pendingPermissions.data && !pendingPermissions.error && (
            <p className="text-sm text-muted text-center py-4">Loading…</p>
          )}
          {pendingPermissions.data && pendingPermissions.data.length === 0 && (
            <div className="py-6 text-center">
              <CheckCircle className="w-10 h-10 text-green-400 mx-auto mb-3" aria-hidden="true" />
              <p className="text-secondary">No pending permissions</p>
              <p className="text-muted text-sm mt-1">Nothing requires your decision</p>
            </div>
          )}
          {pendingPermissions.data?.map((perm) => (
            <PermissionRequestCard key={perm.id} permission={perm} onResolved={handleResolved} />
          ))}
        </CardContent>
      </Card>

      {/* History / audit */}
      <Card variant="container">
        <CardHeader>
          <div className="flex items-center justify-between flex-wrap gap-3">
            <CardTitle className="text-base">Authorization History</CardTitle>
            <div className="flex items-center gap-2 flex-wrap">
              <div className="relative">
                <Search
                  className="w-3.5 h-3.5 text-muted absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
                  aria-hidden="true"
                />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search tool, target…"
                  aria-label="Search authorization history"
                  className="pl-8 py-1.5 text-xs w-44 rounded-lg"
                />
              </div>
              <div
                className="flex items-center gap-1 bg-surface-elevated rounded-xl p-1"
                role="tablist"
                aria-label="Filter by status"
              >
              {STATUS_TABS.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setStatusFilter(tab.id)}
                  role="tab"
                  aria-selected={statusFilter === tab.id}
                  className={cn(
                    'px-3 py-1.5 text-xs font-medium rounded-lg transition-colors focus-ring',
                    statusFilter === tab.id
                      ? 'bg-accent-primary text-white'
                      : 'text-secondary hover:text-primary'
                  )}
                >
                  {tab.label} ({counts[tab.id]})
                </button>
              ))}
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent className="py-0">
          {filtered.length === 0 ? (
            <div className="py-10 text-center">
              <Clock className="w-8 h-8 text-muted mx-auto mb-3" aria-hidden="true" />
              <p className="text-secondary">No {statusFilter !== 'all' ? statusFilter : ''} permission records</p>
            </div>
          ) : (
            <div className="overflow-x-auto scrollbar-thin">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left">
                    <th className="px-3 py-2 text-xs uppercase tracking-wider text-muted font-medium">Time</th>
                    <th className="px-3 py-2 text-xs uppercase tracking-wider text-muted font-medium">Tool</th>
                    <th className="px-3 py-2 text-xs uppercase tracking-wider text-muted font-medium">Operation</th>
                    <th className="px-3 py-2 text-xs uppercase tracking-wider text-muted font-medium">Target</th>
                    <th className="px-3 py-2 text-xs uppercase tracking-wider text-muted font-medium">Risk</th>
                    <th className="px-3 py-2 text-xs uppercase tracking-wider text-muted font-medium">Status</th>
                    <th className="px-3 py-2 text-xs uppercase tracking-wider text-muted font-medium">Conversation</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((perm) => (
                    <tr
                      key={perm.id}
                      className="border-t border-subtle hover:bg-surface-elevated/50 transition-colors"
                    >
                      <td className="px-3 py-2.5 font-mono text-xs text-muted whitespace-nowrap">
                        {formatRelativeTime(perm.created_at)}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-xs text-primary whitespace-nowrap">
                        {perm.tool}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-xs text-secondary whitespace-nowrap">
                        {perm.operation}
                      </td>
                      <td className="px-3 py-2.5 text-xs text-accent-subtle font-mono max-w-[240px] truncate" title={perm.target}>
                        {perm.target}
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        <StatusBadge label={perm.risk_level} tone={riskTone(perm.risk_level)} />
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        <StatusBadge label={perm.status} tone={statusTone(perm.status)} />
                      </td>
                      <td className="px-3 py-2.5 font-mono text-xs text-muted whitespace-nowrap">
                        {perm.conversation_id.slice(0, 8)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function riskTone(risk: string): 'red' | 'orange' | 'amber' | 'cyan' {
  switch (risk) {
    case 'critical':
    case 'high':
      return 'red';
    case 'medium':
      return 'amber';
    default:
      return 'cyan';
  }
}

function statusTone(status: string): 'green' | 'red' | 'orange' | 'muted' {
  switch (status) {
    case 'approved':
      return 'green';
    case 'denied':
      return 'red';
    case 'pending':
      return 'orange';
    default:
      return 'muted';
  }
}

function StatusBadge({ label, tone }: { label: string; tone: ReturnType<typeof riskTone> | ReturnType<typeof statusTone> }) {
  const tones = {
    red: 'bg-red-400/10 text-red-400 border-red-400/20',
    orange: 'bg-accent-primary/10 text-accent-primary border-accent-primary/20',
    amber: 'bg-amber-400/10 text-amber-400 border-amber-400/20',
    cyan: 'bg-accent-subtle/10 text-accent-subtle border-accent-subtle/20',
    green: 'bg-green-400/10 text-green-400 border-green-400/20',
    muted: 'bg-surface-elevated text-muted border-subtle',
  } as const;
  return (
    <span className={cn('inline-flex px-2 py-0.5 rounded-full text-xs font-medium border', tones[tone])}>
      {label}
    </span>
  );
}
