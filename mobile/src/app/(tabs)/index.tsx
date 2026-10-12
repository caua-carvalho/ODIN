import { Text, View, Pressable } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import {
  CloudSun,
  GitBranch,
  FileText,
  Activity,
  Cpu,
  MemoryStick,
  HardDrive,
  Sparkles,
  MessageSquare,
} from 'lucide-react-native';

import { Screen } from '../../components/ui/Screen';
import { Card } from '../../components/ui/Card';
import { StatusBadge } from '../../components/ui/Badges';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import { healthApi } from '../../api/health';
import { briefingApi } from '../../api/briefing';
import { formatRelativeTime, formatBytes, formatUptime } from '../../lib/format';
import type { BriefingResponse } from '../../types/briefing';

function Row({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <View className="flex-row items-center gap-2.5">
      {icon}
      <Text className="text-xs text-muted uppercase tracking-wide w-20">{label}</Text>
      <Text className="flex-1 text-xs text-primary font-mono text-right" numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

export default function DashboardScreen() {
  const router = useRouter();

  const health = useQuery({
    queryKey: ['health'],
    queryFn: healthApi.getHealth,
    refetchInterval: 15_000,
  });

  const briefing = useQuery({
    queryKey: ['briefing'],
    queryFn: briefingApi.getBriefing,
    refetchInterval: 60_000,
  });

  const summary = useQuery({
    queryKey: ['briefing-summary'],
    queryFn: briefingApi.getSummary,
    enabled: false,
  });

  if (health.isLoading) return <Screen title="Dashboard"><Spinner /></Screen>;

  const h = health.data;

  return (
    <Screen
      title="Dashboard"
      right={
        <View className="flex-row items-center gap-2">
          <StatusBadge
            status={h?.agent_ready ? 'ok' : 'err'}
            label={h?.status ?? 'offline'}
          />
        </View>
      }
    >
      {/* Runtime */}
      <Card>
        <Text className="text-xs text-muted uppercase tracking-wider mb-2">Runtime</Text>
        <View className="gap-2.5">
          <Row
            icon={<Cpu size={14} color="#6E6E73" />}
            label="Modelo"
            value={h ? `${h.model_provider} / ${h.model}` : '—'}
          />
          <Row
            icon={<Activity size={14} color="#6E6E73" />}
            label="Tools"
            value={h ? String(h.tools_count) : '—'}
          />
          <Row icon={<HardDrive size={14} color="#6E6E73" />} label="Versão" value={h?.version ?? '—'} />
          <Row icon={<FileText size={14} color="#6E6E73" />} label="Workspace" value={h?.workspace ?? '—'} />
        </View>
      </Card>

      {/* Briefing */}
      {briefing.data ? (
        <BriefingCard
          briefing={briefing.data}
          summary={summary.isFetching ? 'Gerando resumo…' : summary.data?.summary ?? null}
          onSummary={() => void summary.refetch()}
          onOpenChat={() => router.push('/chat')}
        />
      ) : briefing.isError ? (
        <Card className="border-err/30">
          <Text className="text-xs text-err font-medium">Falha ao carregar briefing</Text>
        </Card>
      ) : null}

      {/* System */}
      {briefing.data?.system ? (
        <Card>
          <Text className="text-xs text-muted uppercase tracking-wider mb-2">Sistema</Text>
          <View className="gap-2.5">
            <Row
              icon={<Cpu size={14} color="#6E6E73" />}
              label="CPU"
              value={`${Math.round(briefing.data.system.cpu_percent)}%`}
            />
            <Row
              icon={<MemoryStick size={14} color="#6E6E73" />}
              label="RAM"
              value={`${formatBytes(briefing.data.system.memory_used)} / ${formatBytes(briefing.data.system.memory_total)}`}
            />
            <Row
              icon={<HardDrive size={14} color="#6E6E73" />}
              label="Disco"
              value={`${formatBytes(briefing.data.system.disk_used)} / ${formatBytes(briefing.data.system.disk_total)}`}
            />
            <Row
              icon={<Activity size={14} color="#6E6E73" />}
              label="Uptime"
              value={formatUptime(briefing.data.system.uptime_seconds)}
            />
          </View>
        </Card>
      ) : null}
    </Screen>
  );
}

function BriefingCard({
  briefing,
  summary,
  onSummary,
  onOpenChat,
}: {
  briefing: BriefingResponse;
  summary: string | null;
  onSummary: () => void;
  onOpenChat: () => void;
}) {
  const hasWeather = briefing.weather !== null;
  const gitRepos = (briefing.git ?? []).filter((g): g is NonNullable<typeof g> => g !== null);
  const recentFiles = briefing.files?.recent ?? [];

  return (
    <Card>
      <View className="flex-row items-center justify-between mb-2">
        <Text className="text-xs text-muted uppercase tracking-wider">Briefing</Text>
        <Text className="font-mono text-[10px] text-muted">
          {formatRelativeTime(briefing.generated_at)}
        </Text>
      </View>

      <View className="gap-3">
        {hasWeather && briefing.weather ? (
          <View className="flex-row items-center gap-3">
            <CloudSun size={20} color="#00D9FF" />
            <View className="flex-1">
              <Text className="text-sm text-primary font-medium">{briefing.weather.city}</Text>
              <Text className="text-xs text-secondary">
                {Math.round(briefing.weather.temperature)}° (sensação{' '}
                {Math.round(briefing.weather.apparent)}°) · máx {Math.round(briefing.weather.temp_max)}° ·
                mín {Math.round(briefing.weather.temp_min)}°
              </Text>
            </View>
            <Text className="text-xs text-muted">{briefing.weather.description}</Text>
          </View>
        ) : null}

        {gitRepos.length > 0 ? (
          <View className="gap-2">
            {gitRepos.map((repo, i) => (
              <View key={i} className="flex-row items-center gap-2">
                <GitBranch size={14} color="#6E6E73" />
                <Text className="flex-1 font-mono text-xs text-secondary" numberOfLines={1}>
                  {repo.name}
                </Text>
                <Text className="font-mono text-[10px] text-muted">
                  {repo.changes > 0 ? `${repo.changes} mudanças` : 'limpo'}
                </Text>
              </View>
            ))}
          </View>
        ) : null}

        {recentFiles.length > 0 ? (
          <View className="gap-1.5">
            <Text className="text-[11px] text-muted uppercase tracking-wide">
              Arquivos recentes
            </Text>
            {recentFiles.slice(0, 3).map((f, i) => (
              <Text key={i} className="font-mono text-[11px] text-secondary" numberOfLines={1}>
                {f.path}
              </Text>
            ))}
          </View>
        ) : null}

        {summary ? (
          <View className="bg-surface-container border border-line rounded-xl p-3">
            <Text className="text-xs text-secondary leading-relaxed">{summary}</Text>
          </View>
        ) : null}

        {briefing.conversations.length > 0 ? (
          <Pressable onPress={onOpenChat} className="flex-row items-center gap-2">
            <MessageSquare size={14} color="#FF7A00" />
            <Text className="text-xs text-accent font-medium">
              {briefing.conversations.length} conversa{briefing.conversations.length > 1 ? 's' : ''} recente
              {briefing.conversations.length > 1 ? 's' : ''}
            </Text>
          </Pressable>
        ) : null}

        {!summary ? (
          <Button
            variant="subtle-accent"
            size="sm"
            title="Gerar resumo"
            onPress={onSummary}
          >
            <Sparkles size={14} color="#FF7A00" />
          </Button>
        ) : null}
      </View>
    </Card>
  );
}