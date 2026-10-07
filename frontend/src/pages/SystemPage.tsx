import { usePolling } from '../hooks/usePolling';
import { systemApi } from '../api/system';
import { healthApi } from '../api/health';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { cn, formatBytes, formatUptime } from '../lib/utils';
import { Loader2, AlertTriangle, Cpu, MemoryStick, HardDrive, Activity, Gauge, Server } from 'lucide-react';
import type { SystemInfo } from '../types/system';
import type { HealthResponse } from '../types/health';

export function SystemPage() {
  const system = usePolling<SystemInfo>(() => systemApi.getSystemInfo(), 4000);
  const health = usePolling<HealthResponse>(() => healthApi.getHealth(), 15000);

  if (system.loading && !system.data) {
    return (
      <div className="flex items-center justify-center h-64" role="status" aria-label="Loading system telemetry">
        <Loader2 className="w-6 h-6 text-accent-primary animate-spin" />
      </div>
    );
  }

  if (system.error && !system.data) {
    return (
      <div className="flex items-center justify-center h-64 text-center">
        <div>
          <AlertTriangle className="w-10 h-10 text-accent-secondary mx-auto mb-3" aria-hidden="true" />
          <h2 className="text-lg font-semibold text-primary">OFFLINE</h2>
          <p className="text-sm text-secondary mt-1">Unable to connect to ODIN runtime</p>
          <p className="text-xs text-muted mt-1 font-mono">{system.error}</p>
          <button
            onClick={system.refresh}
            className="mt-4 px-4 py-2 bg-accent-primary text-white rounded-xl text-sm hover:bg-accent-secondary transition-colors focus-ring"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const s = system.data;
  const h = health.data;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-primary tracking-tight">System</h1>
          <p className="text-secondary mt-1">Host runtime telemetry · polled from /api/system</p>
        </div>
        <div className="flex items-center gap-2 text-xs font-mono text-muted">
          <Gauge className="w-3.5 h-3.5 text-accent-subtle" aria-hidden="true" />
          polling every 4s
        </div>
      </div>

      {/* Primary gauges */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <GaugeCard
          icon={Cpu}
          iconClass="text-blue-400"
          label="CPU Utilization"
          percent={s?.cpu_percent ?? 0}
          mainValue={s ? `${s.cpu_percent.toFixed(1)}%` : '—'}
          detail={s ? `load avg ${s.load_avg.map((n) => n.toFixed(2)).join(' · ')}` : ''}
        />
        <GaugeCard
          icon={MemoryStick}
          iconClass="text-green-400"
          label="Memory"
          percent={s?.memory_percent ?? 0}
          mainValue={s ? formatBytes(s.memory_used) : '—'}
          detail={s ? `of ${formatBytes(s.memory_total)} total` : ''}
        />
        <GaugeCard
          icon={HardDrive}
          iconClass="text-amber-400"
          label="Disk"
          percent={s?.disk_percent ?? 0}
          mainValue={s ? formatBytes(s.disk_used) : '—'}
          detail={s ? `of ${formatBytes(s.disk_total)} total` : ''}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Detailed metrics */}
        <Card variant="container">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Activity className="w-4 h-4 text-accent-primary" aria-hidden="true" />
              Metrics Detail
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-0">
            <MetricRow label="cpu_percent" value={s ? s.cpu_percent.toFixed(1) : '—'} />
            <MetricRow label="memory_used" value={s ? `${s.memory_used} B (${formatBytes(s.memory_used)})` : '—'} />
            <MetricRow label="memory_total" value={s ? `${s.memory_total} B (${formatBytes(s.memory_total)})` : '—'} />
            <MetricRow label="memory_percent" value={s ? `${s.memory_percent.toFixed(1)}%` : '—'} />
            <MetricRow label="disk_used" value={s ? `${s.disk_used} B (${formatBytes(s.disk_used)})` : '—'} />
            <MetricRow label="disk_total" value={s ? `${s.disk_total} B (${formatBytes(s.disk_total)})` : '—'} />
            <MetricRow label="disk_percent" value={s ? `${s.disk_percent.toFixed(1)}%` : '—'} />
            <MetricRow label="load_avg[0] (1m)" value={s ? s.load_avg[0].toFixed(2) : '—'} />
            <MetricRow label="load_avg[1] (5m)" value={s ? s.load_avg[1].toFixed(2) : '—'} />
            <MetricRow label="load_avg[2] (15m)" value={s ? s.load_avg[2].toFixed(2) : '—'} />
            <MetricRow
              label="uptime_seconds"
              value={s ? `${s.uptime_seconds.toFixed(0)} s (${formatUptime(s.uptime_seconds)})` : '—'}
            />
          </CardContent>
        </Card>

        {/* Runtime info */}
        <Card variant="container">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Server className="w-4 h-4 text-accent-subtle" aria-hidden="true" />
              Runtime
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-3">
              <InfoRow label="Status" value={h?.status ?? '—'} ok={h?.status === 'online'} />
              <InfoRow label="Agent" value={h?.agent_ready ? 'ready' : 'not ready'} ok={!!h?.agent_ready} />
              <InfoRow label="Version" value={h?.version ?? '—'} ok={!!h?.version} mono />
              <InfoRow label="Provider" value={h?.model_provider ?? '—'} ok={!!h?.model_provider} mono />
              <InfoRow label="Model" value={h?.model ?? '—'} ok={!!h?.model} mono />
              <InfoRow label="Tools count" value={h ? String(h.tools_count) : '—'} ok={!!h} mono />
            </div>
            <div className="pt-3 border-t border-subtle">
              <p className="text-xs uppercase tracking-wider text-muted mb-1">Workspace</p>
              <p className="font-mono text-xs text-accent-subtle break-all">{h?.workspace ?? '—'}</p>
            </div>
            <div className="pt-3 border-t border-subtle text-xs text-muted font-mono space-y-1">
              <p>endpoint: GET /api/system</p>
              <p>endpoint: GET /api/health</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <p className="text-xs text-muted font-mono text-center">
        Only metrics provided by the backend are displayed · no GPU, temperature, network or I/O telemetry exists in the API
      </p>
    </div>
  );
}

function GaugeCard({
  icon: Icon,
  iconClass,
  label,
  percent,
  mainValue,
  detail,
}: {
  icon: typeof Cpu;
  iconClass: string;
  label: string;
  percent: number;
  mainValue: string;
  detail: string;
}) {
  const clamped = Math.min(Math.max(percent, 0), 100);
  return (
    <Card variant="container">
      <CardContent className="py-5">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-surface-elevated rounded-xl">
            <Icon className={cn('w-5 h-5', iconClass)} aria-hidden="true" />
          </div>
          <div>
            <p className="text-xs text-muted">{label}</p>
            <p className="font-mono text-2xl font-bold text-primary tabular-nums">{mainValue}</p>
          </div>
          <span className="ml-auto font-mono text-sm text-secondary tabular-nums">
            {percent.toFixed(1)}%
          </span>
        </div>
        <div
          className="h-1.5 rounded-full bg-surface-elevated overflow-hidden"
          role="progressbar"
          aria-valuenow={Math.round(clamped)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`${label} usage`}
        >
          <div
            className={cn('h-full rounded-full transition-all duration-500', clamped > 85 ? 'bg-red-400' : 'bg-accent-primary')}
            style={{ width: `${clamped}%` }}
          />
        </div>
        <p className="text-xs text-muted mt-2 font-mono">{detail}</p>
      </CardContent>
    </Card>
  );
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-subtle/50 last:border-0">
      <span className="font-mono text-xs text-muted">{label}</span>
      <span className="font-mono text-xs text-primary tabular-nums text-right">{value}</span>
    </div>
  );
}

function InfoRow({ label, value, ok, mono }: { label: string; value: string; ok: boolean; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm text-secondary">{label}</span>
      <div className="flex items-center gap-2 min-w-0">
        <span className={cn('text-primary truncate', mono ? 'font-mono text-sm' : 'text-sm')}>{value}</span>
        <span
          className={cn('w-2 h-2 rounded-full flex-shrink-0', ok ? 'bg-green-400' : 'bg-red-400')}
          aria-hidden="true"
        />
      </div>
    </div>
  );
}
