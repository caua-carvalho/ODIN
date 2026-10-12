import { useEffect, useRef, useState } from 'react';
import { Dialog } from '../ui/Dialog';
import { Button } from '../ui/Button';
import { Input, Textarea } from '../ui/Input';
import { projectsApi } from '../../api/projects';
import { cn } from '../../lib/utils';
import {
  KANBAN_COLUMNS,
  type Task,
  type TaskPriority,
  type TaskStatus,
} from '../../types/project';

interface TaskDialogProps {
  open: boolean;
  projectId: string;
  task?: Task | null;
  defaultStatus?: TaskStatus;
  onClose: () => void;
  onSaved: () => void;
}

const PRIORITIES: { id: TaskPriority; label: string }[] = [
  { id: 'low', label: 'Baixa' },
  { id: 'medium', label: 'Média' },
  { id: 'high', label: 'Alta' },
];

const selectClass =
  'w-full px-3 py-2 bg-surface-elevated border border-subtle rounded-xl text-primary focus-ring transition-colors';

export function TaskDialog({
  open,
  projectId,
  task,
  defaultStatus = 'todo',
  onClose,
  onSaved,
}: TaskDialogProps) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState<TaskStatus>(defaultStatus);
  const [priority, setPriority] = useState<TaskPriority>('medium');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleRef = useRef<HTMLInputElement>(null);

  const isEditing = Boolean(task);

  useEffect(() => {
    if (!open) return;
    setTitle(task?.title ?? '');
    setDescription(task?.description ?? '');
    setStatus(task?.status ?? defaultStatus);
    setPriority(task?.priority ?? 'medium');
    setError(null);
  }, [open, task, defaultStatus]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!title.trim()) {
      setError('Informe um título para a tarefa.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      if (task) {
        await projectsApi.updateTask(task.id, { title: title.trim(), description, status, priority });
      } else {
        await projectsApi.createTask(projectId, { title: title.trim(), description, status, priority });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      labelledBy="task-form-title"
      initialFocusRef={titleRef}
      className="max-w-lg"
    >
      <form onSubmit={handleSubmit} className="p-5 space-y-4">
        <h2 id="task-form-title" className="text-base font-semibold text-primary">
          {isEditing ? 'Editar tarefa' : 'Nova tarefa'}
        </h2>

        <Input
          ref={titleRef}
          label="Título"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="O que precisa ser feito?"
          maxLength={500}
          error={error ?? undefined}
        />

        <Textarea
          label="Descrição"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Opcional"
          rows={3}
        />

        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm">
            <span className="block font-medium text-secondary mb-1.5">Status</span>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as TaskStatus)}
              className={selectClass}
            >
              {KANBAN_COLUMNS.map((column) => (
                <option key={column.id} value={column.id}>
                  {column.label}
                </option>
              ))}
            </select>
          </label>

          <label className="text-sm">
            <span className="block font-medium text-secondary mb-1.5">Prioridade</span>
            <select
              value={priority}
              onChange={(e) => setPriority(e.target.value as TaskPriority)}
              className={selectClass}
            >
              {PRIORITIES.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="flex items-center justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" size="sm" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button type="submit" size="sm" loading={saving}>
            {isEditing ? 'Salvar' : 'Adicionar'}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

const priorityStyles: Record<TaskPriority, string> = {
  low: 'bg-surface-elevated text-muted border-subtle',
  medium: 'bg-accent-primary/10 text-accent-primary border-accent-primary/20',
  high: 'bg-red-400/10 text-red-400 border-red-400/20',
};

const priorityLabels: Record<TaskPriority, string> = {
  low: 'Baixa',
  medium: 'Média',
  high: 'Alta',
};

export function PriorityBadge({ priority, className }: { priority: TaskPriority; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex px-2 py-0.5 rounded-full text-[11px] font-medium border',
        priorityStyles[priority],
        className
      )}
    >
      {priorityLabels[priority]}
    </span>
  );
}
