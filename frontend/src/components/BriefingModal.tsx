import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  CloudRain,
  GitBranch,
  FileText,
  Cpu,
  Server,
  ShieldAlert,
  MessageSquare,
  X,
  Sparkles,
} from 'lucide-react';
import { Dialog } from './ui/Dialog';
import { Card, CardContent, CardHeader, CardTitle } from './ui/Card';
import { Badge } from './ui/Badge';
import { briefingApi } from '../api/briefing';
import { cn, formatBytes, formatUptime, formatRelativeTime } from '../lib/utils';
import type { BriefingResponse } from '../types/briefing';

interface BriefingModalProps {
  open: boolean;
  data: BriefingResponse | null;
  onClose: () => void;
}

/** Portuguese greeting for the given local time. */
function greetingFor(date: Date): string {
  const hour = date.getHours();
  if (hour < 12) return 'Bom dia';
  if (hour < 18) return 'Boa tarde';
  return 'Boa noite';
}

/** Human-readable age from a duration in seconds (PT-BR). */
function formatAge(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s}s atrás`;
  const minutes = Math.floor(s / 60);
  if (minutes < 60) return `${minutes} min atrás`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h atrás`;
  const days = Math.floor(hours / 24);
  return `${days} d atrás`;
}

function round(value: number): number {
  return Math.round(value);
}

/** Small reusable metric row inside the briefing cards. */
function Metric({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-xs text-muted">{label}</span>
      <span className={cn('text-sm font-mono text-primary tabular-nums', className)}>{value}</span>
    </div>
  );
}

export function BriefingModal({ open, data, onClose }: BriefingModalProps) {
  const titleId = 'briefing-modal-title';
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  const [summary, setSummary] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState(false);

  // Fetch the LLM summary as soon as the modal opens with data.
  useEffect(() => {
    if (!open || !data) return;
    let alive = true;
    setSummary(null);
    setSummaryError(false);
    setSummaryLoading(true);
    briefingApi
      .getSummary()
      .then((res) => {
        if (!alive) return;
        setSummary(res.summary);
      })
      .catch(() => {
        if (alive) setSummaryError(true);
      })
      .finally(() => {
        if (alive) setSummaryLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [open, data]);

  const now = useMemo(() => new Date(), [open]);

  const greeting = greetingFor(now);
  const dateLabel = now.toLocaleDateString('pt-BR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  });

  const gitRepos = useMemo(
    () => (data?.git ?? []).filter((repo) => repo !== null),
    [data]
  );

  const recentFiles = useMemo(
    () => (data?.files.recent ?? []).slice(0, 5),
    [data]
  );

  const hasFiles = recentFiles.length > 0 || (data?.files.todo_count ?? 0) > 0;
  const hasPermissions = (data?.permissions.pending ?? 0) > 0 || (data?.permissions.high_risk ?? 0) > 0;
  const hasConversations = (data?.conversations.length ?? 0) > 0;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      labelledBy={titleId}
      initialFocusRef={closeButtonRef}
      className="max-w-3xl"
    >
      <div className="flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 px-6 py-5 border-b border-subtle">
          <div className="min-w-0">
            <h2 id={titleId} className="text-xl font-bold text-primary tracking-tight">
              {greeting}
            </h2>
            <p className="text-sm text-secondary mt-0.5 first-letter:uppercase">{dateLabel}</p>
          </div>
          <button
            ref={closeButtonRef}
            onClick={onClose}
            aria-label="Fechar o briefing"
            className="text-muted hover:text-primary p-1.5 rounded-md focus-ring flex-shrink-0"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="px-6 py-5 overflow-y-auto scrollbar-thin space-y-4">
          {/* LLM summary */}
          {(summaryLoading || summary) && (
            <div className="rounded-2xl border border-accent-primary/20 bg-accent-primary/[0.06] px-4 py-3.5">
              <div className="flex items-center gap-2 mb-1.5">
                <Sparkles className="w-3.5 h-3.5 text-accent-primary" aria-hidden="true" />
                <span className="text-xs font-medium text-accent-primary uppercase tracking-wide">
                  Resumo do dia
                </span>
              </div>
              {summaryLoading ? (
                <div className="space-y-2" role="status" aria-label="Gerando o resumo">
                  <div className="h-3.5 w-full rounded bg-surface-elevated motion-safe:animate-pulse" />
                  <div className="h-3.5 w-4/5 rounded bg-surface-elevated motion-safe:animate-pulse" />
                </div>
              ) : (
                <p className="text-sm text-secondary leading-relaxed whitespace-pre-line">{summary}</p>
              )}
            </div>
          )}
          {summaryError && !summaryLoading && (
            <p className="text-xs text-muted">Não foi possível gerar o resumo agora.</p>
          )}

          {!data && (
            <p className="text-sm text-muted text-center py-6" role="status">
              Carregando o briefing…
            </p>
          )}

          {data && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Weather */}
              {data.weather && (
                <Card variant="container" className="sm:col-span-2">
                  <CardHeader className="flex flex-row items-center gap-2 py-3">
                    <CloudRain className="w-4 h-4 text-cyan-400" aria-hidden="true" />
                    <CardTitle className="text-base">Clima</CardTitle>
                    <span className="ml-auto text-sm text-secondary">{data.weather.city}</span>
                  </CardHeader>
                  <CardContent className="py-3">
                    <div className="flex items-center gap-4">
                      <p className="text-4xl font-bold text-primary tabular-nums">
                        {round(data.weather.temperature)}°
                      </p>
                      <div className="min-w-0">
                        <p className="text-sm text-primary capitalize truncate">
                          {data.weather.description}
                        </p>
                        <p className="text-xs text-muted">
                          Sensação {round(data.weather.apparent)}° · máx {round(data.weather.temp_max)}° ·
                          mín {round(data.weather.temp_min)}°
                        </p>
                      </div>
                      <Badge className="ml-auto flex-shrink-0 bg-cyan-400/10 text-cyan-400 border-cyan-400/20">
                        Chuva {round(data.weather.precipitation_probability)}%
                      </Badge>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Git */}
              {gitRepos.length > 0 && (
                <Card variant="container">
                  <CardHeader className="flex flex-row items-center gap-2 py-3">
                    <GitBranch className="w-4 h-4 text-purple-400" aria-hidden="true" />
                    <CardTitle className="text-base">Repositórios</CardTitle>
                  </CardHeader>
                  <CardContent className="py-3 space-y-3">
                    {gitRepos.map((repo) => (
                      <div key={repo.path} className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-primary truncate">{repo.name}</span>
                          <Badge className="ml-auto flex-shrink-0 bg-surface-elevated text-secondary border border-subtle">
                            {repo.branch}
                          </Badge>
                        </div>
                        <p className="text-xs text-muted font-mono truncate" title={repo.last_commit}>
                          {repo.last_commit}
                        </p>
                        <p className="text-xs text-secondary">
                          {repo.changes} {repo.changes === 1 ? 'alteração' : 'alterações'}
                          {repo.ahead > 0 && ` · ↑${repo.ahead}`}
                          {repo.behind > 0 && ` · ↓${repo.behind}`}
                        </p>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              {/* Files */}
              {hasFiles && (
                <Card variant="container">
                  <CardHeader className="flex flex-row items-center gap-2 py-3">
                    <FileText className="w-4 h-4 text-blue-400" aria-hidden="true" />
                    <CardTitle className="text-base">Arquivos</CardTitle>
                    {data.files.todo_count > 0 && (
                      <Badge className="ml-auto flex-shrink-0 bg-amber-400/10 text-amber-400 border-amber-400/20">
                        {data.files.todo_count} TODOs
                      </Badge>
                    )}
                  </CardHeader>
                  <CardContent className="py-3 space-y-1.5">
                    {recentFiles.map((file) => (
                      <div key={file.path} className="flex items-center justify-between gap-3">
                        <span className="text-xs font-mono text-secondary truncate" title={file.path}>
                          {file.path}
                        </span>
                        <span className="text-xs text-muted flex-shrink-0">{formatAge(file.age_seconds)}</span>
                      </div>
                    ))}
                    {recentFiles.length === 0 && (
                      <p className="text-xs text-muted">Nenhum arquivo recente.</p>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* System */}
              <Card variant="container">
                <CardHeader className="flex flex-row items-center gap-2 py-3">
                  <Cpu className="w-4 h-4 text-green-400" aria-hidden="true" />
                  <CardTitle className="text-base">Sistema</CardTitle>
                </CardHeader>
                <CardContent className="py-3 space-y-2">
                  <Metric label="CPU" value={`${data.system.cpu_percent.toFixed(0)}%`} />
                  <Metric
                    label="Memória"
                    value={`${data.system.memory_percent.toFixed(0)}% · ${formatBytes(data.system.memory_used)}/${formatBytes(data.system.memory_total)}`}
                  />
                  <Metric
                    label="Disco"
                    value={`${data.system.disk_percent.toFixed(0)}% · ${formatBytes(data.system.disk_used)}/${formatBytes(data.system.disk_total)}`}
                  />
                  <Metric label="Uptime" value={formatUptime(data.system.uptime_seconds)} />
                </CardContent>
              </Card>

              {/* Runtime */}
              <Card variant="container">
                <CardHeader className="flex flex-row items-center gap-2 py-3">
                  <Server className="w-4 h-4 text-accent-primary" aria-hidden="true" />
                  <CardTitle className="text-base">Runtime</CardTitle>
                  <span
                    className={cn(
                      'ml-auto w-2 h-2 rounded-full flex-shrink-0',
                      data.runtime.status === 'online' ? 'bg-green-400' : 'bg-red-400'
                    )}
                    aria-hidden="true"
                  />
                </CardHeader>
                <CardContent className="py-3 space-y-2">
                  <Metric label="Provider" value={data.runtime.provider} />
                  <Metric label="Modelo" value={data.runtime.model} />
                  <Metric label="Status" value={data.runtime.status} />
                  <Metric label="Tools" value={String(data.runtime.tools_count)} />
                </CardContent>
              </Card>

              {/* Permissions */}
              {hasPermissions && (
                <Card variant="container" className="border-accent-primary/30">
                  <CardHeader className="flex flex-row items-center gap-2 py-3">
                    <ShieldAlert className="w-4 h-4 text-amber-400" aria-hidden="true" />
                    <CardTitle className="text-base">Permissões</CardTitle>
                  </CardHeader>
                  <CardContent className="py-3">
                    <div className="flex items-center gap-4">
                      <div className="text-center">
                        <p className="text-2xl font-bold text-primary tabular-nums">
                          {data.permissions.pending}
                        </p>
                        <p className="text-xs text-muted">pendentes</p>
                      </div>
                      <div className="text-center">
                        <p className="text-2xl font-bold text-amber-400 tabular-nums">
                          {data.permissions.high_risk}
                        </p>
                        <p className="text-xs text-muted">risco alto</p>
                      </div>
                      <Link
                        to="/permissions"
                        onClick={onClose}
                        className="ml-auto text-sm text-accent-primary hover:text-accent-secondary focus-ring rounded px-2 py-1"
                      >
                        Revisar →
                      </Link>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Recent conversations */}
              {hasConversations && (
                <Card variant="container" className="sm:col-span-2">
                  <CardHeader className="flex flex-row items-center gap-2 py-3">
                    <MessageSquare className="w-4 h-4 text-accent-subtle" aria-hidden="true" />
                    <CardTitle className="text-base">Conversas recentes</CardTitle>
                  </CardHeader>
                  <CardContent className="py-3 divide-y divide-border-subtle">
                    {data.conversations.map((conv) => (
                      <Link
                        key={conv.id}
                        to={`/chat?conversation=${encodeURIComponent(conv.id)}`}
                        onClick={onClose}
                        className="flex items-center justify-between gap-3 py-2 -mx-2 px-2 rounded-lg hover:bg-surface-elevated focus-ring"
                      >
                        <span className="text-sm text-primary truncate" title={conv.title}>
                          {conv.title}
                        </span>
                        <span className="text-xs text-muted flex-shrink-0">
                          {formatRelativeTime(conv.updated_at)}
                        </span>
                      </Link>
                    ))}
                  </CardContent>
                </Card>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end px-6 py-4 border-t border-subtle">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-accent-primary text-white rounded-xl text-sm font-medium hover:bg-accent-secondary transition-[background-color] focus-ring"
          >
            Começar o dia
          </button>
        </div>
      </div>
    </Dialog>
  );
}
