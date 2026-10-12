import { View, Text, Pressable, FlatList } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Lightbulb, Wrench } from 'lucide-react-native';

import { Screen } from '../../../components/ui/Screen';
import { Spinner } from '../../../components/ui/Spinner';
import { EmptyState } from '../../../components/ui/EmptyState';
import { StatusBadge } from '../../../components/ui/Badges';
import { skillsApi } from '../../../api/skills';

export default function SkillsScreen() {
  const router = useRouter();
  const skills = useQuery({ queryKey: ['skills'], queryFn: skillsApi.getSkills });

  return (
    <Screen
      title="Skills"
      subtitle={`${skills.data?.length ?? 0} habilidades disponíveis`}
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
      {skills.isLoading ? (
        <Spinner />
      ) : skills.isError ? (
        <EmptyState title="Falha ao carregar skills" hint={String(skills.error?.message ?? '')} />
      ) : (skills.data ?? []).length === 0 ? (
        <EmptyState icon={<Lightbulb size={28} color="#6E6E73" />} title="Nenhuma skill" />
      ) : (
        <FlatList
          data={skills.data}
          keyExtractor={(s) => s.name}
          className="flex-1"
          contentContainerStyle={{ gap: 10, paddingBottom: 96 }}
          renderItem={({ item }) => (
            <View className="bg-surface-base border border-line rounded-xl px-3.5 py-3 gap-2">
              <View className="flex-row items-start gap-2.5">
                <View className="w-8 h-8 rounded-lg bg-surface-container border border-line items-center justify-center">
                  <Lightbulb size={14} color="#FF9A3D" />
                </View>
                <View className="flex-1 gap-0.5">
                  <Text className="text-sm font-semibold text-primary">{item.name}</Text>
                  <Text className="text-[11px] text-secondary leading-relaxed">{item.description}</Text>
                </View>
                <StatusBadge status={item.enabled ? 'ok' : 'neutral'} label={item.enabled ? 'ativa' : 'inativa'} />
              </View>
              {item.tools.length > 0 ? (
                <View className="flex-row flex-wrap gap-1.5 pl-[42px]">
                  {item.tools.map((tool) => (
                    <View key={tool} className="flex-row items-center gap-1 px-2 py-0.5 rounded-full bg-surface-container border border-line">
                      <Wrench size={9} color="#6E6E73" />
                      <Text className="font-mono text-[10px] text-secondary">{tool}</Text>
                    </View>
                  ))}
                </View>
              ) : null}
            </View>
          )}
        />
      )}
    </Screen>
  );
}