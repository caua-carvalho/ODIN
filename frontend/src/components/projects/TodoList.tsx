import { useMemo, useState } from 'react';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { PriorityBadge, TaskDialog } from './TaskDialog';
import { projectsApi } from '../../api/projects';
import { cn, formatRelativeTime } from '../../lib/utils';
import { Check, Pencil, Plus, Trash2, ClipboardList } from 'lucide-react';
import { KANBAN_COLUMNS, type Task, type TaskStatus } from '../../types/project';

interface TodoListProps {
  projectId: string;
  tasks: Task[];
  onRefresh: () => void;
}

const statusLabels = Object.fromEntries(
  KANBAN_COLUMNS.map((column) => [column.id, column.label])
) as Record<TaskStatus, string>;

export function TodoList({ projectId, tasks, onRefresh }: TodoListProps) {
  const [draft, setDraft] = useState('');
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Task | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [confirmTask, setConfirmTask] = useState<Task | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const { open, done } = useMemo(() => {
    const sorted = [...tasks].sort((a, b) => a.position - b.position);
    return {
      open: sorted.filter((task) => task.status !== 'done'),
      done: sorted.filter((task) => task.status === 'done'),
    };
  }, [tasks]);

  const handleQuickAdd = async (event: React.FormEvent) => {
    event.preventDefault();
    const title = draft.trim();
    if (!title) return;
    setAdding(true);
    try {
      await projectsApi.createTask(projectId, { title });
      setDraft('');
      onRefresh();
    } finally {
      setAdding(false);
    }
  };

  const toggle = async (task: Task) => {
    setBusyId(task.id);
    try {
      await projectsApi.updateTask(task.id, { status: task.status === 'done' ? 'todo' : 'done' });
      onRefresh();
    } finally {
      setBusyId(null);
    }
  };

  const remove = async () => {
    if (!confirmTask) return;
    setBusyId(confirmTask.id);
    try {
      await projectsApi.deleteTask(confirmTask.id);
      setConfirmTask(null);
      onRefresh();
    } finally {
      setBusyId(null);
    }
  };

  const openEdit = (task: Task) => {
    setEditing(task);
    setDialogOpen(true);
  };

  return (
    <div className="space-y-5">
      <form onSubmit={handleQuickAdd} className="flex items-center gap-2">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Adicionar uma tarefa e pressionar Enter…"
          aria-label="Nova tarefa"
        />
        <Button type="submit" size="md" loading={adding} disabled={!draft.trim()}>
          <Plus className="w-4 h-4" aria-hidden="true" />
          Adicionar
        </Button>
      </form>

      {tasks.length === 0 ? (
        <div className="py-12 text-center">
          <ClipboardList className="w-10 h-10 text-muted mx-auto mb-3" aria-hidden="true" />
          <p className="text-secondary">Nenhuma tarefa ainda</p>
          <p className="text-sm text-muted mt-1">Adicione a primeira tarefa acima</p>
        </div>
      ) : (
        <div className="space-y-4">
          <TaskGroup
            title={`A fazer · ${open.length}`}
            tasks={open}
            busyId={busyId}
            onToggle={toggle}
            onEdit={openEdit}
            onDelete={setConfirmTask}
          />
          {done.length > 0 && (
            <TaskGroup
              title={`Concluídas · ${done.length}`}
              tasks={done}
              busyId={busyId}
              onToggle={toggle}
              onEdit={openEdit}
              onDelete={setConfirmTask}
              muted
            />
          )}
        </div>
      )}

      <TaskDialog
        open={dialogOpen}
        projectId={projectId}
        task={editing}
        onClose={() => setDialogOpen(false)}
        onSaved={onRefresh}
      />

      <ConfirmDialog
        open={Boolean(confirmTask)}
        title="Excluir tarefa"
        description={`"${confirmTask?.title ?? ''}" será removida permanentemente.`}
        confirmLabel="Excluir"
        busy={busyId === confirmTask?.id}
        onConfirm={remove}
        onClose={() => setConfirmTask(null)}
      />
    </div>
  );
}

interface TaskGroupProps {
  title: string;
  tasks: Task[];
  busyId: string | null;
  muted?: boolean;
  onToggle: (task: Task) => void;
  onEdit: (task: Task) => void;
  onDelete: (task: Task) => void;
}

function TaskGroup({ title, tasks, busyId, muted, onToggle, onEdit, onDelete }: TaskGroupProps) {
  if (tasks.length === 0) return null;
  return (
    <section>
      <h3 className="text-xs uppercase tracking-wider text-muted mb-2">{title}</h3>
      <ul className="space-y-2">
        {tasks.map((task) => {
          const isDone = task.status === 'done';
          return (
            <li
              key={task.id}
              className={cn(
                'group flex items-start gap-3 px-4 py-3 rounded-xl border border-subtle bg-surface-base',
                'transition-colors hover:bg-surface-elevated/50'
              )}
            >
              <button
                type="button"
                onClick={() => onToggle(task)}
                disabled={busyId === task.id}
                aria-pressed={isDone}
                aria-label={isDone ? 'Marcar como não concluída' : 'Marcar como concluída'}
                className={cn(
                  'mt-0.5 w-5 h-5 rounded-md border flex items-center justify-center flex-shrink-0 transition-colors focus-ring',
                  isDone
                    ? 'bg-green-500 border-green-500 text-white'
                    : 'border-subtle hover:border-accent-primary'
                )}
              >
                {isDone && <Check className="w-3.5 h-3.5" aria-hidden="true" />}
              </button>

              <div className="min-w-0 flex-1">
                <button
                  type="button"
                  onClick={() => onEdit(task)}
                  className="text-left w-full focus-ring rounded"
                >
                  <span
                    className={cn(
                      'block text-sm font-medium',
                      isDone || muted ? 'text-muted line-through' : 'text-primary'
                    )}
                  >
                    {task.title}
                  </span>
                  {task.description && (
                    <span className="block text-xs text-secondary mt-0.5 line-clamp-2">
                      {task.description}
                    </span>
                  )}
                </button>
                <div className="flex items-center gap-2 mt-1.5">
                  <span className="text-[11px] font-mono text-muted">
                    {statusLabels[task.status]}
                  </span>
                  <PriorityBadge priority={task.priority} />
                  <span className="text-[11px] text-muted">
                    {formatRelativeTime(task.updated_at)}
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
                <button
                  type="button"
                  onClick={() => onEdit(task)}
                  aria-label="Editar tarefa"
                  className="p-1.5 rounded-lg text-muted hover:text-primary hover:bg-surface-elevated focus-ring"
                >
                  <Pencil className="w-3.5 h-3.5" aria-hidden="true" />
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(task)}
                  aria-label="Excluir tarefa"
                  className="p-1.5 rounded-lg text-muted hover:text-red-400 hover:bg-red-400/10 focus-ring"
                >
                  <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
