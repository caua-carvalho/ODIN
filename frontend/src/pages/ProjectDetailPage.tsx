import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { projectsApi } from '../api/projects';
import { Button } from '../components/ui/Button';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { ProjectFormDialog } from '../components/projects/ProjectFormDialog';
import { TodoList } from '../components/projects/TodoList';
import { KanbanBoard } from '../components/projects/KanbanBoard';
import { WorkspaceFiles } from '../components/projects/WorkspaceFiles';
import { cn, formatRelativeTime } from '../lib/utils';
import {
  AlertTriangle,
  ArrowLeft,
  CheckSquare,
  FolderOpen,
  Kanban,
  Loader2,
  Pencil,
  Trash2,
} from 'lucide-react';
import type { Project, Task } from '../types/project';

type TabId = 'todo' | 'kanban' | 'workspace';

const TABS: { id: TabId; label: string; icon: typeof CheckSquare }[] = [
  { id: 'todo', label: 'TODO', icon: CheckSquare },
  { id: 'kanban', label: 'Kanban', icon: Kanban },
  { id: 'workspace', label: 'Workspace', icon: FolderOpen },
];

export function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const [project, setProject] = useState<Project | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>('todo');
  const [formOpen, setFormOpen] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const loadProject = useCallback(async () => {
    if (!projectId) return;
    try {
      const data = await projectsApi.get(projectId);
      setProject(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  const loadTasks = useCallback(async () => {
    if (!projectId) return;
    try {
      setTasks(await projectsApi.listTasks(projectId));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [projectId]);

  useEffect(() => {
    setLoading(true);
    void Promise.all([loadProject(), loadTasks()]);
  }, [loadProject, loadTasks]);

  const refresh = useCallback(() => {
    void loadTasks();
    void loadProject();
  }, [loadTasks, loadProject]);

  const completed = useMemo(
    () => tasks.filter((task) => task.status === 'done').length,
    [tasks]
  );

  const handleTabKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const current = TABS.findIndex((item) => item.id === tab);
    let next = current;
    if (event.key === 'ArrowRight') next = (current + 1) % TABS.length;
    else if (event.key === 'ArrowLeft') next = (current - 1 + TABS.length) % TABS.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = TABS.length - 1;
    else return;
    event.preventDefault();
    setTab(TABS[next].id);
  };

  const removeProject = async () => {
    if (!project) return;
    setDeleting(true);
    try {
      await projectsApi.remove(project.id);
      navigate('/projects');
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64" role="status" aria-label="Carregando projeto">
        <Loader2 className="w-6 h-6 text-accent-primary animate-spin" />
      </div>
    );
  }

  if (error || !project || !projectId) {
    return (
      <div className="flex items-center justify-center h-64 text-center">
        <div>
          <AlertTriangle className="w-10 h-10 text-accent-secondary mx-auto mb-3" aria-hidden="true" />
          <h2 className="text-lg font-semibold text-primary">Projeto não encontrado</h2>
          <p className="text-sm text-secondary mt-1 font-mono">{error}</p>
          <Button className="mt-4" variant="secondary" onClick={() => navigate('/projects')}>
            <ArrowLeft className="w-4 h-4" aria-hidden="true" />
            Voltar para projetos
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <button
          type="button"
          onClick={() => navigate('/projects')}
          className="inline-flex items-center gap-1.5 text-sm text-secondary hover:text-primary focus-ring rounded mb-3"
        >
          <ArrowLeft className="w-4 h-4" aria-hidden="true" />
          Projetos
        </button>

        <div className="flex items-start justify-between flex-wrap gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <span
              className="w-4 h-4 rounded-full flex-shrink-0 mt-1.5"
              style={{ backgroundColor: project.color }}
              aria-hidden="true"
            />
            <div className="min-w-0">
              <h1 className="text-2xl font-bold text-primary tracking-tight truncate">
                {project.name}
              </h1>
              <p className="text-secondary mt-1">
                {project.description || 'Sem descrição'}
              </p>
              <p className="text-xs text-muted font-mono mt-1">
                {completed}/{tasks.length} concluídas · atualizado{' '}
                {formatRelativeTime(project.updated_at)}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => setFormOpen(true)}>
              <Pencil className="w-4 h-4" aria-hidden="true" />
              Editar
            </Button>
            <Button variant="danger" size="sm" onClick={() => setConfirmDelete(true)}>
              <Trash2 className="w-4 h-4" aria-hidden="true" />
              Excluir
            </Button>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div
        className="flex items-center gap-1 bg-surface-elevated rounded-xl p-1 w-fit"
        role="tablist"
        aria-label="Seções do projeto"
        onKeyDown={handleTabKeyDown}
      >
        {TABS.map((item) => {
          const Icon = item.icon;
          const active = tab === item.id;
          return (
            <button
              key={item.id}
              id={`project-tab-${item.id}`}
              role="tab"
              aria-selected={active}
              aria-controls={`project-panel-${item.id}`}
              tabIndex={active ? 0 : -1}
              onClick={() => setTab(item.id)}
              className={cn(
                'inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors focus-ring',
                active ? 'bg-accent-primary text-white' : 'text-secondary hover:text-primary'
              )}
            >
              <Icon className="w-4 h-4" aria-hidden="true" />
              {item.label}
            </button>
          );
        })}
      </div>

      {/* Panels */}
      <div
        id={`project-panel-${tab}`}
        role="tabpanel"
        aria-labelledby={`project-tab-${tab}`}
      >
        {tab === 'todo' && (
          <TodoList projectId={projectId} tasks={tasks} onRefresh={refresh} />
        )}
        {tab === 'kanban' && (
          <KanbanBoard projectId={projectId} tasks={tasks} onRefresh={refresh} />
        )}
        {tab === 'workspace' && <WorkspaceFiles projectId={projectId} />}
      </div>

      <ProjectFormDialog
        open={formOpen}
        project={project}
        onClose={() => setFormOpen(false)}
        onSaved={setProject}
      />

      <ConfirmDialog
        open={confirmDelete}
        title="Excluir projeto"
        description={`"${project.name}", suas tarefas e todos os arquivos do workspace serão removidos permanentemente.`}
        confirmLabel="Excluir"
        busy={deleting}
        onConfirm={removeProject}
        onClose={() => setConfirmDelete(false)}
      />
    </div>
  );
}
