import { useState } from 'react';
import { View, Text, FlatList, Pressable, RefreshControl } from 'react-native';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Plus, Pencil, Trash2, CheckCircle2, Circle, Loader2 } from 'lucide-react-native';

import { projectsApi } from '../../api/projects';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { Segmented } from '../ui/Segmented';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { TaskFormDialog } from './TaskFormDialog';
import { PRIORITY_LABELS, STATUS_LABELS, type Task, type TaskStatus } from '../../types/project';
import { cn } from '../../lib/utils';

const STATUS_CYCLE: TaskStatus[] = ['todo', 'doing', 'done'];

const STATUS_ICONS: Record<TaskStatus, { icon: typeof Circle; color: string }> = {
  todo: { icon: Circle, color: '#6E6E73' },
  doing: { icon: Loader2, color: '#00D9FF' },
  done: { icon: CheckCircle2, color: '#34d399' },
};

const PRIORITY_COLORS: Record<string, string> = {
  low: '#6E6E73',
  medium: '#fbbf24',
  high: '#f87171',
};

interface ProjectTodoListProps {
  projectId: string;
  tasks: Task[];
  loading: boolean;
  error: string | null;
  onChanged: () => void;
}

export function ProjectTodoList({ projectId, tasks, loading, error, onChanged }: ProjectTodoListProps) {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<'all' | TaskStatus>('all');
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Task | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Task | null>(null);

  const createMutation = useMutation({
    mutationFn: (data: Parameters<typeof projectsApi.createTask>[1]) =>
      projectsApi.createTask(projectId, data),
    onSuccess: () => {
      setFormOpen(false);
      void queryClient.invalidateQueries({ queryKey: ['tasks', projectId] });
      onChanged();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof projectsApi.updateTask>[1] }) =>
      projectsApi.updateTask(id, data),
    onSuccess: () => {
      setFormOpen(false);
      void queryClient.invalidateQueries({ queryKey: ['tasks', projectId] });
      onChanged();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => projectsApi.deleteTask(id),
    onSuccess: () => {
      setDeleteTarget(null);
      void queryClient.invalidateQueries({ queryKey: ['tasks', projectId] });
      onChanged();
    },
  });

  const cycleStatus = (task: Task) => {
    const next = STATUS_CYCLE[(STATUS_CYCLE.indexOf(task.status) + 1) % STATUS_CYCLE.length];
    updateMutation.mutate({ id: task.id, data: { status: next } });
  };

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };

  const openEdit = (task: Task) => {
    setEditing(task);
    setFormOpen(true);
  };

  const handleConfirm = (data: object) => {
    if (editing) {
      updateMutation.mutate({ id: editing.id, data });
    } else {
      createMutation.mutate(data as Parameters<typeof projectsApi.createTask>[1]);
    }
  };

  const filtered = (filter === 'all' ? tasks : tasks.filter((t) => t.status === filter)).slice().sort(
    (a, b) => a.position - b.position
  );

  return (
    <View className="flex-1 gap-3">
      <Segmented<TaskStatus | 'all'>
        options={[
          { id: 'all', label: 'Todas' },
          { id: 'todo', label: 'A fazer' },
          { id: 'doing', label: 'Em andamento' },
          { id: 'done', label: 'Concluído' },
        ]}
        value={filter}
        onChange={setFilter}
      />

      <View className="flex-row items-center justify-between px-1">
        <Text className="font-mono text-[11px] text-muted">{filtered.length} tarefa{filtered.length === 1 ? '' : 's'}</Text>
        <Button size="sm" variant="subtle-accent" onPress={openCreate}>
          <Plus size={14} color="#FF7A00" />
          <Text className="text-xs font-medium text-accent">Nova</Text>
        </Button>
      </View>

      {loading ? (
        <View className="items-center py-10">
          <Loader2 size={22} color="#FF7A00" />
        </View>
      ) : error ? (
        <EmptyState title="Falha ao carregar tarefas" hint={error} />
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={<Circle size={28} color="#6E6E73" />}
          title={filter === 'all' ? 'Nenhuma tarefa' : `Nenhuma tarefa em "${STATUS_LABELS[filter]}"`}
          hint="Toque em Nova para criar a primeira"
        />
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={(t) => t.id}
          className="flex-1"
          contentContainerStyle={{ gap: 8, paddingBottom: 16 }}
          refreshControl={
            <RefreshControl refreshing={false} onRefresh={onChanged} tintColor="#FF7A00" />
          }
          ItemSeparatorComponent={() => <View className="h-0.5" />}
          renderItem={({ item }) => {
            const StatusIcon = STATUS_ICONS[item.status].icon;
            const statusLabel = STATUS_LABELS[item.status];
            return (
              <Pressable
                onPress={() => cycleStatus(item)}
                onLongPress={() => openEdit(item)}
                className="bg-surface-base border border-line rounded-xl px-3.5 py-3 gap-1.5 active:bg-surface-container"
              >
                <View className="flex-row items-start gap-2.5">
                  <StatusIcon size={18} color={STATUS_ICONS[item.status].color} style={{ marginTop: 1 }} />
                  <View className="flex-1 gap-0.5">
                    <Text
                      className={cn(
                        'text-sm text-primary leading-snug',
                        item.status === 'done' && 'line-through text-muted'
                      )}
                    >
                      {item.title}
                    </Text>
                    <View className="flex-row items-center gap-2">
                      <Text className="font-mono text-[10px] text-muted uppercase">{statusLabel}</Text>
                      <Text
                        className="font-mono text-[10px]"
                        style={{ color: PRIORITY_COLORS[item.priority] }}
                      >
                        {PRIORITY_LABELS[item.priority]}
                      </Text>
                    </View>
                    {item.description ? (
                      <Text className="text-[11px] text-secondary leading-relaxed" numberOfLines={2}>
                        {item.description}
                      </Text>
                    ) : null}
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
          }}
        />
      )}

      <TaskFormDialog
        open={formOpen}
        initial={editing}
        busy={createMutation.isPending || updateMutation.isPending}
        onConfirm={handleConfirm}
        onClose={() => setFormOpen(false)}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Excluir tarefa?"
        description={deleteTarget ? `"${deleteTarget.title}" será removida.` : ''}
        confirmLabel="Excluir"
        danger
        busy={deleteMutation.isPending}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
        onClose={() => setDeleteTarget(null)}
      />
    </View>
  );
}