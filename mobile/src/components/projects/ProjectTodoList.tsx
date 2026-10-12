import { useState } from 'react';
import { View, Text, FlatList, Pressable, RefreshControl } from 'react-native';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Plus,
  Pencil,
  Trash2,
  CheckCircle2,
  Circle,
  Loader2,
  ChevronUp,
  ChevronDown,
} from 'lucide-react-native';

import { projectsApi } from '../../api/projects';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { Segmented } from '../ui/Segmented';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { TaskFormDialog } from './TaskFormDialog';
import {
  PRIORITY_LABELS,
  STATUS_LABELS,
  type Task,
  type TaskReorderItem,
  type TaskStatus,
} from '../../types/project';
import { cn } from '../../lib/utils';

const STATUS_CYCLE: TaskStatus[] = ['todo', 'doing', 'done'];

const STATUS_ICONS: Record<TaskStatus, { icon: typeof Circle; color: string; label: string }> = {
  todo: { icon: Circle, color: '#6E6E73', label: 'A fazer' },
  doing: { icon: Loader2, color: '#00D9FF', label: 'Em andamento' },
  done: { icon: CheckCircle2, color: '#34d399', label: 'Concluído' },
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
  const [refreshing, setRefreshing] = useState(false);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['tasks', projectId] });
    onChanged();
  };

  const createMutation = useMutation({
    mutationFn: (data: Parameters<typeof projectsApi.createTask>[1]) =>
      projectsApi.createTask(projectId, data),
    onSuccess: () => {
      setFormOpen(false);
      invalidate();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof projectsApi.updateTask>[1] }) =>
      projectsApi.updateTask(id, data),
    onSuccess: () => {
      setFormOpen(false);
      invalidate();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => projectsApi.deleteTask(id),
    onSuccess: () => {
      setDeleteTarget(null);
      invalidate();
    },
  });

  const reorderMutation = useMutation({
    mutationFn: (items: TaskReorderItem[]) => projectsApi.reorderTasks(projectId, items),
    onSuccess: invalidate,
  });

  const handleRefresh = () => {
    setRefreshing(true);
    onChanged();
    setTimeout(() => setRefreshing(false), 800);
  };

  /**
   * Move a task up/down within its status group (the same group that is
   * visible in the Kanban column). Positions are re-densified for the group.
   */
  const moveTask = (task: Task, dir: -1 | 1) => {
    const group = tasks
      .filter((t) => t.status === task.status)
      .sort((a, b) => a.position - b.position);
    const idx = group.findIndex((t) => t.id === task.id);
    const targetIdx = idx + dir;
    if (idx < 0 || targetIdx < 0 || targetIdx >= group.length) return;
    const next = [...group];
    [next[idx], next[targetIdx]] = [next[targetIdx], next[idx]];
    reorderMutation.mutate(
      next.map((t, i) => ({ id: t.id, status: t.status, position: i }))
    );
  };

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
          contentContainerStyle={{ gap: 8 }}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} tintColor="#FF7A00" />
          }
          renderItem={({ item }) => {
            const statusMeta = STATUS_ICONS[item.status];
            const StatusIcon = statusMeta.icon;
            return (
              <Pressable
                onPress={() => openEdit(item)}
                className="bg-surface-base border border-line rounded-xl px-3.5 py-3 gap-1.5 active:bg-surface-container"
                accessibilityLabel={`Editar tarefa ${item.title}`}
              >
                <View className="flex-row items-start gap-2.5">
                  <Pressable
                    onPress={() => cycleStatus(item)}
                    hitSlop={10}
                    className="pt-0.5 pr-1"
                    accessibilityLabel={`Alterar status da tarefa ${item.title} (atualmente ${statusMeta.label})`}
                    accessibilityRole="button"
                  >
                    <StatusIcon size={18} color={statusMeta.color} style={{ marginTop: 1 }} />
                  </Pressable>
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
                      <Text className="font-mono text-[10px] text-muted uppercase">{statusMeta.label}</Text>
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
                  <View className="flex-row items-center gap-0.5 pt-0.5">
                    <View className="gap-0.5">
                      <Pressable
                        onPress={() => moveTask(item, -1)}
                        hitSlop={8}
                        className="p-0.5"
                        disabled={reorderMutation.isPending}
                        accessibilityLabel={`Mover ${item.title} para cima`}
                        accessibilityRole="button"
                      >
                        <ChevronUp size={14} color="#6E6E73" />
                      </Pressable>
                      <Pressable
                        onPress={() => moveTask(item, 1)}
                        hitSlop={8}
                        className="p-0.5"
                        disabled={reorderMutation.isPending}
                        accessibilityLabel={`Mover ${item.title} para baixo`}
                        accessibilityRole="button"
                      >
                        <ChevronDown size={14} color="#6E6E73" />
                      </Pressable>
                    </View>
                    <Pressable
                      onPress={() => openEdit(item)}
                      hitSlop={8}
                      className="p-1"
                      accessibilityLabel={`Editar tarefa ${item.title}`}
                    >
                      <Pencil size={14} color="#6E6E73" />
                    </Pressable>
                    <Pressable
                      onPress={() => setDeleteTarget(item)}
                      hitSlop={8}
                      className="p-1"
                      accessibilityLabel={`Excluir tarefa ${item.title}`}
                    >
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