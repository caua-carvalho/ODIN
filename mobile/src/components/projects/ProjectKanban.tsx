import { useCallback, useState } from 'react';
import { View, Text, ScrollView, Pressable } from 'react-native';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Draggable, Droppable, DropProvider } from 'react-native-reanimated-dnd';
import { Plus, Circle, Loader2, CheckCircle2 } from 'lucide-react-native';

import { projectsApi } from '../../api/projects';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { TaskFormDialog } from './TaskFormDialog';
import {
  KANBAN_COLUMNS,
  PRIORITY_LABELS,
  type Task,
  type TaskStatus,
} from '../../types/project';
import { cn } from '../../lib/utils';

const PRIORITY_BAR: Record<string, string> = {
  low: '#6E6E73',
  medium: '#fbbf24',
  high: '#f87171',
};

interface ProjectKanbanProps {
  projectId: string;
  tasks: Task[];
  loading: boolean;
  error: string | null;
  onChanged: () => void;
}

export function ProjectKanban({ projectId, tasks, loading, error, onChanged }: ProjectKanbanProps) {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);

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
      void queryClient.invalidateQueries({ queryKey: ['tasks', projectId] });
      onChanged();
    },
  });

  /**
   * Real drag & drop between columns: each column is a `Droppable` zone and
   * every card is a `Draggable`. Dropping a card on another column moves the
   * task to the end of that column.
   */
  const handleDrop = useCallback(
    (task: Task, column: TaskStatus) => {
      if (task.status === column) return;
      const targetColumn = tasks
        .filter((t) => t.status === column)
        .sort((a, b) => a.position - b.position);
      const position = (targetColumn.at(-1)?.position ?? -1) + 1;
      updateMutation.mutate({ id: task.id, data: { status: column, position } });
    },
    [tasks, updateMutation]
  );

  const handleAdd = (data: object) => {
    createMutation.mutate(data as Parameters<typeof projectsApi.createTask>[1]);
  };

  if (loading) {
    return (
      <View className="items-center py-10">
        <Loader2 size={22} color="#FF7A00" />
      </View>
    );
  }

  if (error) {
    return <EmptyState title="Falha ao carregar tarefas" hint={error} />;
  }

  return (
    <View className="flex-1 gap-3">
      <View className="flex-row items-center justify-between px-1">
        <Text className="font-mono text-[11px] text-muted">
          Arraste um cartão para mover entre colunas
        </Text>
        <Button size="sm" variant="subtle-accent" onPress={() => setFormOpen(true)}>
          <Plus size={14} color="#FF7A00" />
          <Text className="text-xs font-medium text-accent">Nova</Text>
        </Button>
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: 10, paddingHorizontal: 4, paddingBottom: 16 }}
      >
        <DropProvider>
          <View className="flex-row gap-3">
            {KANBAN_COLUMNS.map((column) => {
              const columnTasks = tasks
                .filter((t) => t.status === column.id)
                .sort((a, b) => a.position - b.position);

              return (
                <Droppable<Task>
                  key={column.id}
                  droppableId={column.id}
                  onDrop={(task) => handleDrop(task, column.id)}
                  activeStyle={{ backgroundColor: 'rgba(255,122,0,0.06)', borderColor: '#FF7A00' }}
                >
                  <View className="w-64 bg-surface-container border border-line rounded-2xl overflow-hidden">
                    {/* Column header */}
                    <View className="px-3 py-2.5 flex-row items-center justify-between border-b border-line">
                      <Text className="text-xs font-semibold text-primary uppercase tracking-wide">
                        {column.label}
                      </Text>
                      <View className="px-2 py-0.5 rounded-full bg-surface-elevated">
                        <Text className="font-mono text-[10px] text-secondary">{columnTasks.length}</Text>
                      </View>
                    </View>

                    {/* Cards */}
                    <View className="p-2 gap-2 min-h-[160px]">
                      {columnTasks.map((task) => (
                        <Draggable key={task.id} data={task} preDragDelay={120}>
                          <KanbanCard task={task} />
                        </Draggable>
                      ))}
                      {columnTasks.length === 0 ? (
                        <View className="items-center py-8">
                          <Text className="text-[11px] text-muted">Solte cartões aqui</Text>
                        </View>
                      ) : null}
                    </View>
                  </View>
                </Droppable>
              );
            })}
          </View>
        </DropProvider>
      </ScrollView>

      <TaskFormDialog
        open={formOpen}
        busy={createMutation.isPending}
        onConfirm={handleAdd}
        onClose={() => setFormOpen(false)}
      />
    </View>
  );
}

function KanbanCard({ task }: { task: Task }) {
  const isDone = task.status === 'done';
  return (
    <Pressable
      className={cn(
        'bg-surface-base border border-line rounded-xl px-3 py-2.5 gap-1.5',
        isDone && 'opacity-60'
      )}
    >
      <View className="flex-row items-start gap-2">
        <View className="w-1 self-stretch rounded-full" style={{ backgroundColor: PRIORITY_BAR[task.priority] }} />
        <Text className="flex-1 text-xs text-primary leading-snug" numberOfLines={3}>
          {task.title}
        </Text>
      </View>
      <View className="flex-row items-center justify-between">
        <Text className="font-mono text-[9px] uppercase" style={{ color: PRIORITY_BAR[task.priority] }}>
          {PRIORITY_LABELS[task.priority]}
        </Text>
        {isDone ? <CheckCircle2 size={12} color="#34d399" /> : <Circle size={12} color="#6E6E73" />}
      </View>
    </Pressable>
  );
}