import { useState } from 'react';
import { Text, View, ScrollView, KeyboardAvoidingView, Platform } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import Constants from 'expo-constants';
import { CheckCircle2, XCircle, Server } from 'lucide-react-native';

import { Input } from '../components/ui/Input';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { probeHealth } from '../api/health';
import { useServerConfig } from '../providers/config';
import type { HealthResponse } from '../types/health';

/** Default port the backend runs on (`ODIN_PORT` in the backend `.env`). */
const BACKEND_PORT = 8000;

/**
 * Best-effort default for the server URL. When the app runs under the Expo dev
 * server (Expo Go on a phone, or Expo web), `hostUri` is the Metro host:port,
 * e.g. `192.168.1.6:8081`. Reuse only its host with the backend's port so the
 * IP is always correct and the user just has to confirm the port. Returns ''
 * when there is no dev host (e.g. a production build), forcing manual input.
 */
function defaultServerUrl(): string {
  const host = Constants.expoConfig?.hostUri?.split(':')[0];
  if (!host) return '';
  if (host === 'localhost' || host === '127.0.0.1' || host === '0.0.0.0') {
    return `http://localhost:${BACKEND_PORT}`;
  }
  return `http://${host}:${BACKEND_PORT}`;
}

export default function ConnectScreen() {
  const { configure } = useServerConfig();

  const [url, setUrl] = useState(defaultServerUrl);
  const [token, setToken] = useState('');
  const [testing, setTesting] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    message: string;
    health?: HealthResponse;
  } | null>(null);

  const runTest = async (): Promise<HealthResponse | null> => {
    if (!url.trim()) {
      setTestResult({ ok: false, message: 'Informe a URL do servidor.' });
      return null;
    }
    setTesting(true);
    setTestResult(null);
    try {
      const health = await probeHealth(url, token.trim() || undefined);
      setTestResult({
        ok: true,
        health,
        message: `Conectado — ${health.model_provider}/${health.model}`,
      });
      return health;
    } catch (err) {
      setTestResult({ ok: false, message: err instanceof Error ? err.message : String(err) });
      return null;
    } finally {
      setTesting(false);
    }
  };

  const handleConnect = async () => {
    setConnecting(true);
    try {
      const health = await runTest();
      if (!health) return;
      // Persisting the config flips the root `Stack.Protected` guard, which
      // removes this screen and reveals the `(tabs)` navigator. No manual
      // navigation is needed (and doing it here would race React's commit).
      await configure({ url, token });
    } finally {
      setConnecting(false);
    }
  };

  return (
    <SafeAreaView className="flex-1 bg-surface-canvas">
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        className="flex-1"
      >
        <ScrollView
          className="flex-1"
          contentContainerStyle={{ padding: 20, gap: 16, justifyContent: 'center', flexGrow: 1 }}
          keyboardShouldPersistTaps="handled"
        >
          <View className="items-center gap-2 mb-2">
            <View className="w-14 h-14 rounded-2xl bg-accent/10 border border-accent/30 items-center justify-center">
              <Server size={28} color="#FF7A00" />
            </View>
            <Text className="text-2xl font-bold text-primary tracking-tight">ODIN</Text>
            <Text className="text-center text-sm text-secondary leading-relaxed">
              Conecte o app ao seu servidor Odin. Em um celular, use o IP da máquina na rede (ex.
              http://&lt;ip-da-maquina&gt;:8000) e garanta que o backend rode com ODIN_HOST=0.0.0.0.
            </Text>
          </View>

          <View className="gap-3">
            <Input
              label="URL do servidor"
              placeholder="http://<ip-da-maquina>:8000"
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              value={url}
              onChangeText={setUrl}
            />
            <Input
              label="Token (opcional)"
              placeholder="Bearer token, se habilitado no backend"
              autoCapitalize="none"
              autoCorrect={false}
              secureTextEntry
              value={token}
              onChangeText={setToken}
            />
          </View>

          {testResult ? (
            <Card
              className={
                testResult.ok
                  ? 'border-ok/30 bg-ok/5'
                  : 'border-err/30 bg-err/5'
              }
            >
              <View className="flex-row items-start gap-2">
                {testResult.ok ? (
                  <CheckCircle2 size={18} color="#34d399" />
                ) : (
                  <XCircle size={18} color="#f87171" />
                )}
                <View className="flex-1 gap-1">
                  <Text
                    className={testResult.ok ? 'text-xs text-ok font-medium' : 'text-xs text-err font-medium'}
                  >
                    {testResult.message}
                  </Text>
                  {testResult.ok && testResult.health ? (
                    <Text className="font-mono text-[11px] text-muted">
                      v{testResult.health.version} · {testResult.health.tools_count} tools ·{' '}
                      {testResult.health.agent_ready ? 'agent pronto' : 'agent indisponível'}
                    </Text>
                  ) : null}
                </View>
              </View>
            </Card>
          ) : null}

          <View className="gap-2">
            <Button
              title="Testar conexão"
              variant="secondary"
              loading={testing}
              onPress={() => void runTest()}
            />
            <Button
              title="Conectar"
              loading={connecting}
              onPress={() => void handleConnect()}
            />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}