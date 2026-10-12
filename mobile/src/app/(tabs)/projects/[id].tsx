import { useState } from 'react';
import { View, Text, Pressable } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ArrowLeft, Pencil, Trash2 } from 'lucide-react-native';

import { projectsApi } from '../../../api/projects';
import { Segmented } from '../../../components/ui/Segmented';
import { Spinner } from '../../../components/ui/Spinner';
import { EmptyState } from '../../../components/ui/EmptyState';
import { ConfirmDialog } from '../../../components/ui/ConfirmDialog';
import { ProjectFormDialog } from '../../../components/projects/ProjectFormDialog';
import { ProjectTodoList } from '../../../components/projects/ProjectTodoList';
import { ProjectKanban } from '../../../components/projects/ProjectKanban';
import { ProjectWorkspace } from '../../../components/projects/ProjectWorkspace';
import { formatRelativeTime } from '../../../lib/format';

type ViewMode = 'todo' | 'kanban' | 'workspace';

const viewOptions: { id: ViewMode; label: string }[] = [
  { id: 'todo', label: 'TODO' },
  { id: 'kanban', label: 'Kanban' },
  { id: 'workspace', label: 'Arquivos' },
];

export default function ProjectDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const [view, setView] = useState<ViewMode>('todo');
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const projectId = typeof id === 'string' ? id : '';

  const project = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => projectsApi.get(projectId),
    enabled: !!projectId,
  });

  const tasks = useQuery({
    queryKey: ['tasks', projectId],
    queryFn: () => projectsApi.listTasks(projectId),
    enabled: !!projectId && view !== 'workspace',
    refetchInterval: 10_000,
  });

  const invalidateProject = () => {
    void queryClient.invalidateQueries({ queryKey: ['project', projectId] });
    void queryClient.invalidateQueries({ queryKey: ['projects'] });
  };

  const updateMutation = useMutation({
    mutationFn: ({ data }: { data: Parameters<typeof projectsApi.update>[1] }) =>
      projectsApi.update(projectId, data),
    onSuccess: () => {
      setEditOpen(false);
      invalidateProject();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => projectsApi.remove(projectId),
    onSuccess: () => {
      setDeleteOpen(false);
      void queryClient.invalidateQueries({ queryKey: ['projects'] });
      router.back();
    },
  });

  if (project.isLoading) {
    return (
      <SafeAreaView edges={['top']} className="flex-1 bg-surface-canvas">
        <Spinner />
      </SafeAreaView>
    );
  }

  if (project.isError || !project.data) {
    return (
      <SafeAreaView edges={['top']} className="flex-1 bg-surface-canvas">
        <EmptyState
          title="Falha ao carregar projeto"
          hint={String(project.error?.message ?? 'Não encontrado')}
        />
      </SafeAreaView>
    );
  }

  const p = project.data;

  return (
    <SafeAreaView edges={['top']} className="flex-1 bg-surface-canvas">
      {/* Header */}
      <View className="px-4 py-2.5 flex-row items-center gap-3 border-b border-line bg-surface-base">
        <Pressable onPress={() => router.back()} hitSlop={10} className="p-1">
          <ArrowLeft size={20} color="#A1A1A6" />
        </Pressable>
        <View className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: p.color }} />
        <View className="flex-1 min-w-0">
          <Text className="text-sm font-semibold text-primary" numberOfLines={1}>
            {p.name}
          </Text>
          <Text className="font-mono text-[10px] text-muted">
            {p.task_count} tarefas · atualizado {formatRelativeTime(p.updated_at)}
          </Text>
        </View>
        <Pressable onPress={() => setEditOpen(true)} hitSlop={10} className="p-2">
          <Pencil size={16} color="#6E6E73" />
        </Pressable>
        <Pressable onPress={() => setDeleteOpen(true)} hitSlop={10} className="p-2">
          <Trash2 size={16} color="#6E6E73" />
        </Pressable>
      </View>

      {p.description ? (
        <View className="px-4 pt-2">
          <Text className="text-xs text-secondary leading-relaxed">{p.description}</Text>
        </View>
      ) : null}

      <View className="px-4 py-3">
        <Segmented options={viewOptions} value={view} onChange={setView} />
      </View>

      <View className="flex-1 px-2 pb-2">
        {view === 'workspace' ? (
          <ProjectWorkspace projectId={projectId} />
        ) : view === 'kanban' ? (
          <ProjectKanban
            projectId={projectId}
            tasks={tasks.data ?? []}
            loading={tasks.isLoading}
            error={tasks.isError ? String(tasks.error?.message ?? '') : null}
            onChanged={() => invalidateProject()}
          />
        ) : (
          <ProjectTodoList
            projectId={projectId}
            tasks={tasks.data ?? []}
            loading={tasks.isLoading}
            error={tasks.isError ? String(tasks.error?.message ?? '') : null}
            onChanged={() => invalidateProject()}
          />
        )}
      </View>

      <ProjectFormDialog
        open={editOpen}
        initial={p}
        busy={updateMutation.isPending}
        onConfirm={(data) => updateMutation.mutate({ data })}
        onClose={() => setEditOpen(false)}
      />

      <ConfirmDialog
        open={deleteOpen}
        title="Excluir projeto?"
        description={`"${p.name}" e todo o seu workspace serão removidos permanentemente.`}
        confirmLabel="Excluir"
        danger
        busy={deleteMutation.isPending}
        onConfirm={() => deleteMutation.mutate()}
        onClose={() => setDeleteOpen(false)}
      />
    </SafeAreaView>
  );
}