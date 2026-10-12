import { View, Text, Pressable } from 'react-native';
import { useRouter } from 'expo-router';
import {
  Wrench,
  Lightbulb,
  Activity,
  Settings,
  ChevronRight,
  Server,
} from 'lucide-react-native';

import { Screen } from '../../../components/ui/Screen';
import { Card } from '../../../components/ui/Card';
import { useServerConfig } from '../../../providers/config';
import { truncateMiddle } from '../../../lib/format';

const items = [
  { href: '/more/tools', icon: Wrench, label: 'Tools', hint: 'Ferramentas disponíveis para o agente' },
  { href: '/more/skills', icon: Lightbulb, label: 'Skills', hint: 'Habilidades do agente' },
  { href: '/more/system', icon: Activity, label: 'Sistema', hint: 'CPU, memória, disco, uptime' },
  { href: '/more/settings', icon: Settings, label: 'Configurações', hint: 'Servidor, modelo e conexão' },
] as const;

export default function MoreScreen() {
  const router = useRouter();
  const { config } = useServerConfig();

  return (
    <Screen title="Mais">
      {config ? (
        <Card className="py-3">
          <View className="flex-row items-center gap-2.5">
            <View className="w-9 h-9 rounded-xl bg-surface-container border border-line items-center justify-center">
              <Server size={16} color="#FF7A00" />
            </View>
            <View className="flex-1 min-w-0">
              <Text className="text-xs text-secondary" numberOfLines={1}>
                Conectado a
              </Text>
              <Text className="text-sm font-medium text-primary" numberOfLines={1}>
                {config.url.replace(/^https?:\/\//, '')}
              </Text>
            </View>
            {config.token ? (
              <Text className="font-mono text-[10px] text-muted">token: {truncateMiddle(config.token, 8)}</Text>
            ) : (
              <Text className="font-mono text-[10px] text-warn">sem token</Text>
            )}
          </View>
        </Card>
      ) : null}

      <View className="gap-2">
        {items.map(({ href, icon: Icon, label, hint }) => (
          <Pressable
            key={href}
            onPress={() => router.push(href)}
            className="bg-surface-base border border-line rounded-2xl px-4 py-3.5 flex-row items-center gap-3 active:bg-surface-container"
          >
            <View className="w-9 h-9 rounded-xl bg-surface-container border border-line items-center justify-center">
              <Icon size={17} color="#F5F5F7" />
            </View>
            <View className="flex-1 gap-0.5">
              <Text className="text-sm font-semibold text-primary">{label}</Text>
              <Text className="text-[11px] text-muted">{hint}</Text>
            </View>
            <ChevronRight size={16} color="#3a3a40" />
          </Pressable>
        ))}
      </View>
    </Screen>
  );
}