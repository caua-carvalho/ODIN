import { useState } from 'react';
import { View, Text, FlatList, Pressable, RefreshControl } from 'react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { Plus, FolderKanban, Pencil, Trash2 } from 'lucide-react-native';

import { Screen } from '../../../components/ui/Screen';
import { Button } from '../../../components/ui/Button';
import { Spinner } from '../../../components/ui/Spinner';
import { EmptyState } from '../../../components/ui/EmptyState';
import { ProgressBar } from '../../../components/ui/ProgressBar';
import { ConfirmDialog } from '../../../components/ui/ConfirmDialog';
import { ProjectFormDialog } from '../../../components/projects/ProjectFormDialog';
import { projectsApi } from '../../../api/projects';
import { formatRelativeTime } from '../../../lib/format';
import type { Project } from '../../../types/project';

export default function ProjectsScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);

  const projects = useQuery({
    queryKey: ['projects'],
    queryFn: projectsApi.list,
    refetchInterval: 30_000,
  });

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['projects'] });
  };

  const createMutation = useMutation({
    mutationFn: projectsApi.create,
    onSuccess: invalidate,
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof projectsApi.update>[1] }) =>
      projectsApi.update(id, data),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => projectsApi.remove(id),
    onSuccess: invalidate,
  });

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };

  const openEdit = (project: Project) => {
    setEditing(project);
    setFormOpen(true);
  };

  const handleConfirm = (data: object) => {
    if (editing) {
      updateMutation.mutate({ id: editing.id, data }, { onSettled: () => setFormOpen(false) });
    } else {
      createMutation.mutate(data as Parameters<typeof projectsApi.create>[0], {
        onSettled: () => setFormOpen(false),
      });
    }
  };

  const confirmDelete = () => {
    if (!deleteTarget) return;
    deleteMutation.mutate(deleteTarget.id);
    setDeleteTarget(null);
  };

  const renderItem = ({ item }: { item: Project }) => {
    const progress = item.task_count > 0 ? (item.done_count / item.task_count) * 100 : 0;
    return (
      <Pressable
        onPress={() => router.push(`/projects/${item.id}`)}
        className="flex-1 m-1 bg-surface-base border border-line rounded-2xl overflow-hidden active:bg-surface-container"
      >
        <View style={{ backgroundColor: item.color }} className="h-1" />
        <View className="p-3.5 gap-2">
          <View className="flex-row items-start gap-1.5 pr-6">
            <View className="w-2 h-2 rounded-full mt-1" style={{ backgroundColor: item.color }} />
            <Text className="flex-1 text-sm font-semibold text-primary" numberOfLines={1}>
              {item.name}
            </Text>
          </View>
          {item.description ? (
            <Text className="text-[11px] text-secondary leading-relaxed" numberOfLines={2}>
              {item.description}
            </Text>
          ) : null}
          <View className="gap-1.5">
            <View className="flex-row justify-between">
              <Text className="font-mono text-[10px] text-muted">{item.done_count}/{item.task_count}</Text>
              <Text className="font-mono text-[10px] text-muted">{formatRelativeTime(item.updated_at)}</Text>
            </View>
            <ProgressBar percent={progress} />
          </View>
          <View className="flex-row gap-3 pt-0.5">
            <Pressable onPress={() => openEdit(item)} hitSlop={8} className="p-1">
              <Pencil size={14} color="#6E6E73" />
            </Pressable>
            <Pressable onPress={() => setDeleteTarget(item)} hitSlop={8} className="p-1">
              <Trash2 size={14} color="#6E6E73" />
            </Pressable>
          </View>
        </View>
      </Pressable>
    );
  };

  return (
    <Screen
      title="Projetos"
      subtitle="TODO, Kanban e workspace de arquivos"
      right={
        <Button size="sm" variant="subtle-accent" onPress={openCreate}>
          <Plus size={16} color="#FF7A00" />
        </Button>
      }
    >
      {projects.isLoading ? (
        <Spinner />
      ) : projects.isError ? (
        <EmptyState title="Falha ao carregar projetos" hint={String(projects.error?.message ?? '')} />
      ) : (projects.data ?? []).length === 0 ? (
        <EmptyState
          icon={<FolderKanban size={32} color="#6E6E73" />}
          title="Nenhum projeto ainda"
          hint="Crie o primeiro projeto para organizar tarefas e arquivos"
        />
      ) : (
        <FlatList
          data={projects.data}
          keyExtractor={(p) => p.id}
          numColumns={2}
          className="flex-1"
          contentContainerStyle={{ paddingBottom: 16, paddingHorizontal: 4 }}
          refreshControl={
            <RefreshControl
              refreshing={projects.isRefetching}
              onRefresh={() => void projects.refetch()}
              tintColor="#FF7A00"
            />
          }
          renderItem={renderItem}
        />
      )}

      <ProjectFormDialog
        open={formOpen}
        initial={editing}
        busy={createMutation.isPending || updateMutation.isPending}
        onConfirm={handleConfirm}
        onClose={() => setFormOpen(false)}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Excluir projeto?"
        description={
          deleteTarget
            ? `"${deleteTarget.name}" e todo o seu workspace (arquivos, tarefas) serão removidos permanentemente.`
            : ''
        }
        confirmLabel="Excluir"
        danger
        busy={deleteMutation.isPending}
        onConfirm={confirmDelete}
        onClose={() => setDeleteTarget(null)}
      />
    </Screen>
  );
}