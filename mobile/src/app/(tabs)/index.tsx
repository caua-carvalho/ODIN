import { Text, View, Pressable, Modal, ScrollView } from 'react-native';
import { useEffect, useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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
  ShieldCheck,
  X,
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
  const queryClient = useQueryClient();
  const [briefingOpen, setBriefingOpen] = useState(false);
  const ackedForBootRef = useRef(false);

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
    retry: 0,
  });

  const ackMutation = useMutation({
    mutationFn: briefingApi.ackBriefing,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['briefing'] });
    },
  });

  // Open the boot-once briefing. Once dismissed it is ack'd to the backend, so
  // it does not reappear for the same boot (mirrors the web panel).
  useEffect(() => {
    const data = briefing.data;
    if (!ackedForBootRef.current && data?.should_show) {
      ackedForBootRef.current = true;
      setBriefingOpen(true);
    }
  }, [briefing.data]);

  const dismissBriefing = () => {
    setBriefingOpen(false);
    // Ack so the backend stops reporting should_show for this boot.
    if (briefing.data?.should_show && !ackMutation.isPending) {
      ackMutation.mutate();
    }
  };

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
          summary={summary.data?.summary ?? null}
          generating={summary.isFetching}
          summaryError={summary.isError ? String(summary.error?.message ?? '') : null}
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

      {/* Boot-once briefing modal */}
      <Modal visible={briefingOpen} transparent animationType="fade" onRequestClose={dismissBriefing}>
        <View className="flex-1 bg-black/70 items-center justify-center px-6">
          <View className="w-full max-w-sm bg-surface-base border border-line rounded-2xl max-h-[85%] overflow-hidden">
            <View className="px-5 pt-4 pb-2 flex-row items-center justify-between border-b border-line">
              <Text className="text-base font-bold text-primary">Briefing do servidor</Text>
              <Pressable onPress={dismissBriefing} hitSlop={10} className="p-1" accessibilityLabel="Fechar briefing">
                <X size={18} color="#A1A1A6" />
              </Pressable>
            </View>
            <ScrollView className="flex-1" showsVerticalScrollIndicator={false}>
              {briefing.data ? <BriefingModalBody briefing={briefing.data} /> : null}
            </ScrollView>
            <View className="px-5 py-3 border-t border-line">
              <Button title="Entendi" onPress={dismissBriefing} loading={ackMutation.isPending} />
            </View>
          </View>
        </View>
      </Modal>
    </Screen>
  );
}

function BriefingCard({
  briefing,
  summary,
  generating,
  summaryError,
  onSummary,
  onOpenChat,
}: {
  briefing: BriefingResponse;
  summary: string | null;
  generating: boolean;
  summaryError: string | null;
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

        {generating ? (
          <Text className="text-xs text-secondary font-mono">Gerando resumo…</Text>
        ) : summary ? (
          <View className="bg-surface-container border border-line rounded-xl p-3">
            <Text className="text-xs text-secondary leading-relaxed">{summary}</Text>
          </View>
        ) : null}

        {summaryError ? (
          <Text className="text-[11px] font-mono text-err">{summaryError}</Text>
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

        {!generating ? (
          <Button
            variant="subtle-accent"
            size="sm"
            title={summary ? 'Atualizar resumo' : 'Gerar resumo'}
            onPress={onSummary}
          >
            <Sparkles size={14} color="#FF7A00" />
          </Button>
        ) : null}
      </View>
    </Card>
  );
}

/** Compact, read-only version of the briefing shown inside the boot-once modal. */
function BriefingModalBody({ briefing }: { briefing: BriefingResponse }) {
  const hasWeather = briefing.weather !== null;
  const gitRepos = (briefing.git ?? []).filter((g): g is NonNullable<typeof g> => g !== null);
  const recentFiles = briefing.files?.recent ?? [];

  return (
    <View className="px-5 py-4 gap-3">
      {hasWeather && briefing.weather ? (
        <View className="flex-row items-center gap-3">
          <CloudSun size={18} color="#00D9FF" />
          <View className="flex-1">
            <Text className="text-sm text-primary font-medium">{briefing.weather.city}</Text>
            <Text className="text-xs text-secondary">
              {Math.round(briefing.weather.temperature)}° (sensação {Math.round(briefing.weather.apparent)}°) ·
              máx {Math.round(briefing.weather.temp_max)}° · mín {Math.round(briefing.weather.temp_min)}°
            </Text>
          </View>
        </View>
      ) : null}

      {gitRepos.length > 0 ? (
        <View className="gap-2">
          <Text className="text-[11px] text-muted uppercase tracking-wide">Repositórios</Text>
          {gitRepos.map((repo, i) => (
            <View key={i} className="flex-row items-center gap-2">
              <GitBranch size={13} color="#6E6E73" />
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
          <Text className="text-[11px] text-muted uppercase tracking-wide">Arquivos recentes</Text>
          {recentFiles.slice(0, 3).map((f, i) => (
            <Text key={i} className="font-mono text-[11px] text-secondary" numberOfLines={1}>
              {f.path}
            </Text>
          ))}
        </View>
      ) : null}

      <View className="flex-row flex-wrap gap-2 pt-1">
        <View className="flex-row items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-container border border-line">
          <Cpu size={11} color="#00D9FF" />
          <Text className="font-mono text-[11px] text-secondary">
            CPU {Math.round(briefing.system.cpu_percent)}%
          </Text>
        </View>
        <View className="flex-row items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-container border border-line">
          <MemoryStick size={11} color="#FF9A3D" />
          <Text className="font-mono text-[11px] text-secondary">
            {formatBytes(briefing.system.memory_used)} RAM
          </Text>
        </View>
        <View className="flex-row items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-container border border-line">
          <ShieldCheck size={11} color="#fbbf24" />
          <Text className="font-mono text-[11px] text-secondary">
            {briefing.permissions.pending} permissões pendentes
          </Text>
        </View>
        <View className="flex-row items-center gap-1.5 px-2.5 py-1 rounded-full bg-surface-container border border-line">
          <MessageSquare size={11} color="#FF7A00" />
          <Text className="font-mono text-[11px] text-secondary">
            {briefing.conversations.length} conversas
          </Text>
        </View>
      </View>
    </View>
  );
}