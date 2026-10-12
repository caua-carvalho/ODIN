import { useState } from 'react';
import { View, Text, FlatList, RefreshControl } from 'react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ShieldCheck, Shield, Check, X } from 'lucide-react-native';

import { Screen } from '../../components/ui/Screen';
import { Segmented } from '../../components/ui/Segmented';
import { RiskBadge, StatusBadge } from '../../components/ui/Badges';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import { EmptyState } from '../../components/ui/EmptyState';
import { permissionsApi } from '../../api/permissions';
import { formatRelativeTime } from '../../lib/format';
import type { PermissionRequest } from '../../types/permission';

export default function PermissionsScreen() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<'pending' | 'all'>('pending');

  const permissions = useQuery({
    queryKey: ['permissions', filter],
    queryFn: () =>
      filter === 'pending'
        ? permissionsApi.listPendingPermissions()
        : permissionsApi.listPermissions(),
    refetchInterval: filter === 'pending' ? 5000 : 30_000,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['permissions'] });
    void queryClient.invalidateQueries({ queryKey: ['briefing'] });
  };

  const approveMutation = useMutation({
    mutationFn: (id: string) => permissionsApi.approvePermission(id),
    onSuccess: invalidate,
  });

  const denyMutation = useMutation({
    mutationFn: (id: string) => permissionsApi.denyPermission(id),
    onSuccess: invalidate,
  });

  const act = (permission: PermissionRequest, approve: boolean) => {
    (approve ? approveMutation : denyMutation).mutate(permission.id);
  };

  return (
    <Screen
      title="Permissões"
      subtitle="Aprovações de segurança para operações do agente"
      right={
        <StatusBadge
          status={(permissions.data ?? []).some((p) => p.status === 'pending') ? 'warn' : 'ok'}
          label={String((permissions.data ?? []).filter((p) => p.status === 'pending').length)}
        />
      }
    >
      <Segmented
        options={[
          { id: 'pending', label: 'Pendentes' },
          { id: 'all', label: 'Histórico' },
        ]}
        value={filter}
        onChange={setFilter}
      />

      {permissions.isLoading ? (
        <Spinner />
      ) : permissions.isError ? (
        <EmptyState title="Falha ao carregar permissões" hint={String(permissions.error?.message ?? '')} />
      ) : (permissions.data ?? []).length === 0 ? (
        <EmptyState
          icon={<ShieldCheck size={32} color="#6E6E73" />}
          title={filter === 'pending' ? 'Nenhuma aprovação pendente' : 'Nenhum registro'}
          hint="Operações fora do workspace exigem aprovação"
        />
      ) : (
        <FlatList
          data={permissions.data}
          keyExtractor={(p) => p.id}
          className="flex-1"
          contentContainerStyle={{ gap: 8, paddingBottom: 16 }}
          refreshControl={
            <RefreshControl
              refreshing={permissions.isRefetching}
              onRefresh={() => void permissions.refetch()}
              tintColor="#FF7A00"
            />
          }
          ItemSeparatorComponent={() => <View className="h-0.5" />}
          renderItem={({ item }) => {
            let args: unknown = null;
            try {
              args = JSON.parse(item.arguments_json);
            } catch {
              args = item.arguments_json;
            }
            const isPending = item.status === 'pending';
            return (
              <View className="bg-surface-base border border-line rounded-xl px-3.5 py-3 gap-2">
                <View className="flex-row items-start gap-2.5">
                  <Shield size={16} color={isPending ? '#FF7A00' : '#6E6E73'} style={{ marginTop: 1 }} />
                  <View className="flex-1 gap-0.5">
                    <Text className="font-mono text-xs text-primary font-medium">
                      {item.tool} · {item.operation}
                    </Text>
                    <Text className="text-[11px] text-secondary" numberOfLines={2}>
                      {item.target}
                    </Text>
                  </View>
                </View>

                {item.reason ? (
                  <Text className="text-[11px] text-muted leading-relaxed" numberOfLines={2}>
                    {item.reason}
                  </Text>
                ) : null}

                {args !== null && args !== undefined && typeof args === 'object' && Object.keys(args as object).length > 0 ? (
                  <Text className="font-mono text-[10px] text-muted" numberOfLines={3}>
                    {JSON.stringify(args).slice(0, 300)}
                  </Text>
                ) : null}

                <View className="flex-row items-center justify-between">
                  <View className="flex-row items-center gap-2">
                    <RiskBadge level={item.risk_level} />
                    {!isPending ? (
                      <StatusBadge
                        status={item.status === 'approved' ? 'ok' : item.status === 'denied' ? 'err' : 'neutral'}
                        label={item.status}
                      />
                    ) : null}
                    <Text className="font-mono text-[10px] text-muted">
                      {formatRelativeTime(item.created_at)}
                    </Text>
                  </View>

                  {isPending ? (
                    <View className="flex-row gap-2">
                      <Button
                        size="sm"
                        title="Aprovar"
                        loading={approveMutation.isPending && approveMutation.variables === item.id}
                        onPress={() => act(item, true)}
                      >
                        <Check size={13} color="#050505" />
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        title="Negar"
                        disabled={denyMutation.isPending && denyMutation.variables === item.id}
                        onPress={() => act(item, false)}
                      >
                        <X size={13} color="#A1A1A6" />
                      </Button>
                    </View>
                  ) : (
                    <Text className="font-mono text-[10px] text-muted">
                      {item.resolved_at ? formatRelativeTime(item.resolved_at) : ''}
                    </Text>
                  )}
                </View>
              </View>
            );
          }}
        />
      )}
    </Screen>
  );
}