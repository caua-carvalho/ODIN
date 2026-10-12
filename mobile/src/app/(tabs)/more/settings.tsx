import { useState } from 'react';
import { View, Text, Pressable, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Server, CheckCircle2, XCircle, LogOut, RefreshCw } from 'lucide-react-native';

import { Screen } from '../../../components/ui/Screen';
import { Card } from '../../../components/ui/Card';
import { Input } from '../../../components/ui/Input';
import { Button } from '../../../components/ui/Button';
import { ConfirmDialog } from '../../../components/ui/ConfirmDialog';
import { StatusBadge } from '../../../components/ui/Badges';
import { useServerConfig } from '../../../providers/config';
import { healthApi, probeHealth } from '../../../api/health';
import { providersApi } from '../../../api/providers';
import { cn } from '../../../lib/utils';

export default function SettingsScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { config, configure, reset } = useServerConfig();

  const [url, setUrl] = useState(config?.url ?? '');
  const [token, setToken] = useState(config?.token ?? '');
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);
  const [logoutOpen, setLogoutOpen] = useState(false);

  const providers = useQuery({ queryKey: ['providers'], queryFn: providersApi.list, retry: 1 });
  const health = useQuery({ queryKey: ['health'], queryFn: healthApi.getHealth });

  const selectMutation = useMutation({
    mutationFn: ({ provider, model }: { provider: string; model: string }) =>
      providersApi.select(provider, model),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['providers'] });
      void queryClient.invalidateQueries({ queryKey: ['health'] });
    },
  });

  const runTest = async (): Promise<boolean> => {
    if (!url.trim()) {
      setTestResult({ ok: false, message: 'Informe a URL do servidor.' });
      return false;
    }
    setTesting(true);
    setTestResult(null);
    try {
      const healthData = await probeHealth(url, token.trim() || undefined);
      setTestResult({
        ok: true,
        message: `Conectado — ${healthData.model_provider}/${healthData.model} (${healthData.tools_count} tools)`,
      });
      return true;
    } catch (err) {
      setTestResult({ ok: false, message: err instanceof Error ? err.message : String(err) });
      return false;
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    if (!url.trim()) return;
    setSaving(true);
    try {
      const ok = await runTest();
      if (!ok) return;
      await configure({ url, token });
      setTestResult({ ok: true, message: 'Configuração salva.' });
    } finally {
      setSaving(false);
    }
  };

  const handleLogout = async () => {
    setLogoutOpen(false);
    await reset();
    router.replace('/connect');
  };

  const active = providers.data?.active;

  return (
    <Screen
      title="Configurações"
      right={
        <Pressable onPress={() => router.back()} hitSlop={10} className="p-1">
          <ArrowLeft size={20} color="#A1A1A6" />
        </Pressable>
      }
    >
      {/* Server */}
      <Card className="gap-3">
        <View className="flex-row items-center gap-2">
          <Server size={16} color="#FF7A00" />
          <Text className="text-sm font-semibold text-primary">Servidor</Text>
          {health.isSuccess ? (
            <StatusBadge status={health.data?.agent_ready ? 'ok' : 'warn'} label={health.data?.status ?? 'offline'} />
          ) : null}
        </View>

        <Input label="URL do servidor" placeholder="http://192.168.0.10:8000" autoCapitalize="none" autoCorrect={false} keyboardType="url" value={url} onChangeText={setUrl} />
        <Input label="Token (opcional)" placeholder="Bearer token do backend" autoCapitalize="none" autoCorrect={false} secureTextEntry value={token} onChangeText={setToken} />

        {testResult ? (
          <View className={cn('flex-row items-start gap-2 rounded-xl border px-3 py-2', testResult.ok ? 'border-ok/30 bg-ok/5' : 'border-err/30 bg-err/5')}>
            {testResult.ok ? <CheckCircle2 size={16} color="#34d399" /> : <XCircle size={16} color="#f87171" />}
            <Text className={cn('flex-1 text-xs font-medium', testResult.ok ? 'text-ok' : 'text-err')}>
              {testResult.message}
            </Text>
          </View>
        ) : null}

        <View className="flex-row gap-2">
          <Button variant="secondary" className="flex-1" title="Testar" loading={testing} onPress={() => void runTest()} />
          <Button className="flex-1" title="Salvar" loading={saving} disabled={!url.trim()} onPress={() => void handleSave()} />
        </View>
      </Card>

      {/* Model */}
      <Card className="gap-3">
        <Text className="text-sm font-semibold text-primary">Modelo ativo</Text>
        {active ? (
          <View className="flex-row items-center gap-2 bg-surface-container border border-line rounded-xl px-3 py-2.5">
            <RefreshCw size={14} color="#00D9FF" />
            <Text className="flex-1 font-mono text-xs text-primary" numberOfLines={1}>
              {active.provider} / {active.model}
            </Text>
          </View>
        ) : null}

        {providers.isLoading ? (
          <Text className="text-xs text-muted">Carregando provedores…</Text>
        ) : providers.isError ? (
          <Text className="text-xs text-err">Falha ao listar provedores.</Text>
        ) : (
          <View className="gap-2">
            {providers.data?.providers
              .filter((p) => p.configured)
              .map((provider) => (
                <View key={provider.id} className="gap-1.5">
                  <View className="flex-row items-center justify-between px-1">
                    <Text className="text-xs font-semibold text-secondary">{provider.label}</Text>
                    {active?.provider === provider.id ? <StatusBadge status="ok" label="ativo" /> : null}
                  </View>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                    <View className="flex-row gap-1.5">
                      {provider.models.map((model) => {
                        const isActive = active?.provider === provider.id && active?.model === model;
                        return (
                          <Pressable
                            key={model}
                            onPress={() => selectMutation.mutate({ provider: provider.id, model })}
                            className={cn(
                              'px-3 py-1.5 rounded-full border',
                              isActive ? 'bg-accent/10 border-accent/40' : 'bg-surface-container border-line'
                            )}
                          >
                            <Text className={cn('font-mono text-[11px]', isActive ? 'text-accent' : 'text-secondary')}>
                              {model}
                            </Text>
                          </Pressable>
                        );
                      })}
                    </View>
                  </ScrollView>
                </View>
              ))}
          </View>
        )}
        {selectMutation.isError ? (
          <Text className="text-[11px] font-mono text-err">{String(selectMutation.error?.message ?? '')}</Text>
        ) : null}
      </Card>

      {/* About + logout */}
      <Card className="gap-2">
        <View className="flex-row items-center justify-between">
          <Text className="text-xs font-medium text-secondary">Odin Mobile</Text>
          <Text className="font-mono text-[10px] text-muted">v1.0.0 · Expo SDK</Text>
        </View>
        <Text className="text-[11px] text-muted leading-relaxed">
          Cliente móvel para o assistente Odin. Aponte para o backend em sua rede
          (ODIN_HOST=0.0.0.0) e, se habilitado, informe o token de segurança.
        </Text>
        <Button variant="ghost" title="Desconectar servidor" onPress={() => setLogoutOpen(true)}>
          <LogOut size={14} color="#f87171" />
        </Button>
      </Card>

      <ConfirmDialog
        open={logoutOpen}
        title="Desconectar?"
        description="O app voltará para a tela de conexão. Seu servidor continua rodando."
        confirmLabel="Desconectar"
        danger
        onConfirm={() => void handleLogout()}
        onClose={() => setLogoutOpen(false)}
      />
    </Screen>
  );
}