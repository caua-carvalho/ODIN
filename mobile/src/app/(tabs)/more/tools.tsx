import { useMemo, useState } from 'react';
import { View, Text, Pressable, FlatList } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Wrench, Lock, ChevronDown, ChevronRight } from 'lucide-react-native';

import { Screen } from '../../../components/ui/Screen';
import { Spinner } from '../../../components/ui/Spinner';
import { EmptyState } from '../../../components/ui/EmptyState';
import { toolsApi } from '../../../api/tools';
import type { ToolDefinition } from '../../../types/tool';
import { cn } from '../../../lib/utils';

export default function ToolsScreen() {
  const router = useRouter();
  const tools = useQuery({ queryKey: ['tools'], queryFn: toolsApi.getTools });
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const grouped = useMemo(() => {
    const map = new Map<string, ToolDefinition[]>();
    for (const tool of tools.data ?? []) {
      const key = tool.category || 'Outros';
      const list = map.get(key) ?? [];
      list.push(tool);
      map.set(key, list);
    }
    return Array.from(map.entries());
  }, [tools.data]);

  return (
    <Screen
      title="Tools"
      subtitle={`${tools.data?.length ?? 0} ferramentas registradas`}
      scroll={false}
      right={
        <Pressable
          onPress={() => router.back()}
          hitSlop={10}
          className="p-1"
          accessibilityLabel="Voltar"
        >
          <ArrowLeft size={20} color="#A1A1A6" />
        </Pressable>
      }
    >
      {tools.isLoading ? (
        <Spinner />
      ) : tools.isError ? (
        <EmptyState title="Falha ao carregar tools" hint={String(tools.error?.message ?? '')} />
      ) : (
        <FlatList
          data={grouped}
          keyExtractor={([category]) => category}
          className="flex-1"
          contentContainerStyle={{ gap: 12, paddingBottom: 96 }}
          renderItem={({ item: [category, list] }) => (
            <View className="gap-2">
              <Text className="px-1 text-xs font-semibold text-muted uppercase tracking-wider">
                {category}
              </Text>
              {list.map((tool) => {
                const isOpen = !!expanded[tool.name];
                const paramNames = Object.keys(tool.parameters_schema?.properties ?? {});
                return (
                  <View key={tool.name} className="bg-surface-base border border-line rounded-xl overflow-hidden">
                    <Pressable
                      onPress={() => setExpanded((s) => ({ ...s, [tool.name]: !s[tool.name] }))}
                      className="px-3.5 py-3 flex-row items-center gap-2.5 active:bg-surface-container"
                    >
                      <View className="w-8 h-8 rounded-lg bg-surface-container border border-line items-center justify-center">
                        <Wrench size={14} color="#00D9FF" />
                      </View>
                      <View className="flex-1 gap-0.5">
                        <Text className="font-mono text-xs text-primary font-medium">{tool.name}</Text>
                        {!isOpen ? (
                          <Text className="text-[11px] text-muted" numberOfLines={1}>
                            {tool.description}
                          </Text>
                        ) : null}
                      </View>
                      {tool.requires_approval_by_default ? (
                        <View className="flex-row items-center gap-1 px-1.5 py-0.5 rounded-full bg-warn/10">
                          <Lock size={9} color="#fbbf24" />
                          <Text className="text-[9px] font-semibold text-warn uppercase">aprovação</Text>
                        </View>
                      ) : null}
                      {isOpen ? <ChevronDown size={14} color="#3a3a40" /> : <ChevronRight size={14} color="#3a3a40" />}
                    </Pressable>

                    {isOpen ? (
                      <View className="px-3.5 pb-3 gap-2">
                        <Text className="text-[11px] text-secondary leading-relaxed">{tool.description}</Text>
                        {paramNames.length > 0 ? (
                          <View className="gap-1">
                            <Text className="text-[10px] text-muted uppercase tracking-wide">Parâmetros</Text>
                            {paramNames.map((name) => {
                              const prop = tool.parameters_schema.properties[name];
                              const required = tool.parameters_schema.required?.includes(name);
                              return (
                                <View key={name} className="flex-row items-start gap-2">
                                  <Text className={cn('font-mono text-[11px]', required ? 'text-accent' : 'text-secondary')}>
                                    {name}
                                  </Text>
                                  <Text className="flex-1 text-[11px] text-muted" numberOfLines={2}>
                                    {prop?.description ?? prop?.type ?? ''}
                                    {prop?.enum ? ` [${prop.enum.join(', ')}]` : ''}
                                  </Text>
                                </View>
                              );
                            })}
                          </View>
                        ) : null}
                      </View>
                    ) : null}
                  </View>
                );
              })}
            </View>
          )}
        />
      )}
    </Screen>
  );
}