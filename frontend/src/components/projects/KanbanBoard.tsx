import { useEffect, useState } from 'react';
import { PriorityBadge, TaskDialog } from './TaskDialog';
import { projectsApi } from '../../api/projects';
import { cn } from '../../lib/utils';
import { GripVertical, Pencil, Plus } from 'lucide-react';
import {
  KANBAN_COLUMNS,
  type Task,
  type TaskReorderItem,
  type TaskStatus,
} from '../../types/project';

interface KanbanBoardProps {
  projectId: string;
  tasks: Task[];
  onRefresh: () => void;
}

type Board = Record<TaskStatus, Task[]>;

function groupTasks(tasks: Task[]): Board {
  const columns: Board = { todo: [], doing: [], done: [] };
  for (const task of [...tasks].sort((a, b) => a.position - b.position)) {
    (columns[task.status] ?? columns.todo).push(task);
  }
  return columns;
}

const STATUSES: TaskStatus[] = ['todo', 'doing', 'done'];

export function KanbanBoard({ projectId, tasks, onRefresh }: KanbanBoardProps) {
  const [board, setBoard] = useState<Board>(() => groupTasks(tasks));
  const [dragId, setDragId] = useState<string | null>(null);
  const [overColumn, setOverColumn] = useState<TaskStatus | null>(null);
  const [dropIndex, setDropIndex] = useState<number | null>(null);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Task | null>(null);
  const [dialogStatus, setDialogStatus] = useState<TaskStatus>('todo');

  // Re-sync from the server whenever the source list changes.
  useEffect(() => {
    setBoard(groupTasks(tasks));
  }, [tasks]);

  const resetDrag = () => {
    setDragId(null);
    setOverColumn(null);
    setDropIndex(null);
  };

  const commitMove = (targetStatus: TaskStatus) => {
    if (!dragId) {
      resetDrag();
      return;
    }

    const next: Board = {
      todo: [...board.todo],
      doing: [...board.doing],
      done: [...board.done],
    };

    const sourceStatus = STATUSES.find((status) =>
      next[status].some((task) => task.id === dragId)
    );
    if (!sourceStatus) {
      resetDrag();
      return;
    }

    const originalIndex = next[sourceStatus].findIndex((task) => task.id === dragId);
    const [moved] = next[sourceStatus].splice(originalIndex, 1);

    let insertAt = dropIndex ?? next[targetStatus].length;
    if (sourceStatus === targetStatus && dropIndex != null && originalIndex < dropIndex) {
      insertAt -= 1;
    }

    next[targetStatus].splice(insertAt, 0, { ...moved, status: targetStatus });

    const touched: TaskStatus[] = sourceStatus === targetStatus
      ? [targetStatus]
      : [sourceStatus, targetStatus];
    const updates: TaskReorderItem[] = [];
    for (const status of touched) {
      next[status] = next[status].map((task, index) => {
        updates.push({ id: task.id, status, position: index });
        return { ...task, status, position: index };
      });
    }

    setBoard(next);
    resetDrag();
    projectsApi
      .reorderTasks(projectId, updates)
      .then(onRefresh)
      .catch(() => onRefresh());
  };

  const openCreate = (status: TaskStatus) => {
    setEditing(null);
    setDialogStatus(status);
    setDialogOpen(true);
  };

  const openEdit = (task: Task) => {
    setEditing(task);
    setDialogStatus(task.status);
    setDialogOpen(true);
  };

  return (
    <div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {KANBAN_COLUMNS.map((column) => {
          const items = board[column.id];
          const isOver = overColumn === column.id && dragId !== null;
          return (
            <div
              key={column.id}
              onDragOver={(event) => {
                event.preventDefault();
                setOverColumn(column.id);
                setDropIndex(null);
              }}
              onDrop={(event) => {
                event.preventDefault();
                commitMove(column.id);
              }}
              className={cn(
                'rounded-[20px] border bg-surface-container flex flex-col min-h-[320px] transition-colors',
                isOver ? 'border-accent-primary/60 bg-accent-primary/5' : 'border-subtle'
              )}
            >
              <div className="flex items-center justify-between px-4 py-3 border-b border-subtle">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-primary">{column.label}</span>
                  <span className="text-xs font-mono text-muted">{items.length}</span>
                </div>
                <button
                  type="button"
                  onClick={() => openCreate(column.id)}
                  aria-label={`Adicionar tarefa em ${column.label}`}
                  className="p-1 rounded-lg text-muted hover:text-primary hover:bg-surface-elevated focus-ring"
                >
                  <Plus className="w-4 h-4" aria-hidden="true" />
                </button>
              </div>

              <ul className="flex-1 p-3 space-y-2">
                {items.map((task, index) => (
                  <li
                    key={task.id}
                    draggable
                    onDragStart={(event) => {
                      setDragId(task.id);
                      event.dataTransfer.effectAllowed = 'move';
                      event.dataTransfer.setData('text/plain', task.id);
                    }}
                    onDragOver={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      setOverColumn(column.id);
                      setDropIndex(index);
                    }}
                    onDragEnd={resetDrag}
                    className={cn(
                      'group rounded-xl border border-subtle bg-surface-base p-3 cursor-grab active:cursor-grabbing',
                      'transition-shadow hover:shadow-[0_4px_16px_rgba(0,0,0,0.3)]',
                      dragId === task.id && 'opacity-50'
                    )}
                  >
                    <div className="flex items-start gap-2">
                      <GripVertical
                        className="w-4 h-4 text-muted flex-shrink-0 mt-0.5"
                        aria-hidden="true"
                      />
                      <button
                        type="button"
                        onClick={() => openEdit(task)}
                        className="min-w-0 flex-1 text-left focus-ring rounded"
                      >
                        <span className="block text-sm font-medium text-primary break-words">
                          {task.title}
                        </span>
                        {task.description && (
                          <span className="block text-xs text-secondary mt-0.5 line-clamp-2">
                            {task.description}
                          </span>
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => openEdit(task)}
                        aria-label="Editar tarefa"
                        className="p-1 rounded-lg text-muted hover:text-primary focus-ring opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <Pencil className="w-3.5 h-3.5" aria-hidden="true" />
                      </button>
                    </div>
                    <div className="mt-2 pl-6">
                      <PriorityBadge priority={task.priority} />
                    </div>
                  </li>
                ))}

                {items.length === 0 && (
                  <li className="text-xs text-muted text-center py-6 select-none">
                    Solte uma tarefa aqui
                  </li>
                )}
              </ul>
            </div>
          );
        })}
      </div>

      <TaskDialog
        open={dialogOpen}
        projectId={projectId}
        task={editing}
        defaultStatus={dialogStatus}
        onClose={() => setDialogOpen(false)}
        onSaved={onRefresh}
      />
    </div>
  );
}
