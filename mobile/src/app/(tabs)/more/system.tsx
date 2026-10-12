import { View, Text, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Cpu, MemoryStick, HardDrive, Activity, RefreshCw } from 'lucide-react-native';

import { Screen } from '../../../components/ui/Screen';
import { Card } from '../../../components/ui/Card';
import { ProgressBar } from '../../../components/ui/ProgressBar';
import { Spinner } from '../../../components/ui/Spinner';
import { EmptyState } from '../../../components/ui/EmptyState';
import { Button } from '../../../components/ui/Button';
import { systemApi } from '../../../api/system';
import { formatBytes, formatUptime } from '../../../lib/format';

export default function SystemScreen() {
  const router = useRouter();
  const system = useQuery({
    queryKey: ['system'],
    queryFn: systemApi.getSystemInfo,
    refetchInterval: 10_000,
  });

  return (
    <Screen
      title="Sistema"
      right={
        <Pressable onPress={() => router.back()} hitSlop={10} className="p-1">
          <ArrowLeft size={20} color="#A1A1A6" />
        </Pressable>
      }
    >
      {system.isLoading ? (
        <Spinner />
      ) : system.isError ? (
        <EmptyState
          title="Falha ao carregar sistema"
          hint={String(system.error?.message ?? '')}
        />
      ) : system.data ? (
        <>
          <MetricCard
            icon={<Cpu size={16} color="#00D9FF" />}
            label="CPU"
            value={`${Math.round(system.data.cpu_percent)}%`}
            percent={system.data.cpu_percent}
          />
          <MetricCard
            icon={<MemoryStick size={16} color="#FF9A3D" />}
            label="Memória"
            value={`${formatBytes(system.data.memory_used)} / ${formatBytes(system.data.memory_total)}`}
            percent={system.data.memory_percent}
          />
          <MetricCard
            icon={<HardDrive size={16} color="#34d399" />}
            label="Disco"
            value={`${formatBytes(system.data.disk_used)} / ${formatBytes(system.data.disk_total)}`}
            percent={system.data.disk_percent}
          />

          <Card>
            <Text className="text-xs text-muted uppercase tracking-wider mb-2">Informações</Text>
            <View className="gap-2.5">
              <InfoRow icon={<Activity size={14} color="#6E6E73" />} label="Uptime" value={formatUptime(system.data.uptime_seconds)} />
              <InfoRow
                icon={<Cpu size={14} color="#6E6E73" />}
                label="Load avg"
                value={system.data.load_avg.map((v) => v.toFixed(2)).join(' / ')}
              />
            </View>
          </Card>

          <Button
            variant="ghost"
            title="Atualizar"
            onPress={() => void system.refetch()}
          >
            <RefreshCw size={14} color="#A1A1A6" />
          </Button>
        </>
      ) : null}
    </Screen>
  );
}

function MetricCard({
  icon,
  label,
  value,
  percent,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  percent: number;
}) {
  return (
    <Card className="gap-2.5">
      <View className="flex-row items-center justify-between">
        <View className="flex-row items-center gap-2">
          {icon}
          <Text className="text-xs font-medium text-secondary">{label}</Text>
        </View>
        <Text className="font-mono text-sm text-primary">{value}</Text>
      </View>
      <ProgressBar percent={percent} />
    </Card>
  );
}

function InfoRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <View className="flex-row items-center gap-2.5">
      {icon}
      <Text className="text-xs text-muted uppercase tracking-wide w-24">{label}</Text>
      <Text className="flex-1 font-mono text-xs text-primary text-right" numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}