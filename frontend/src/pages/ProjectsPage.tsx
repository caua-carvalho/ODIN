import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePolling } from '../hooks/usePolling';
import { projectsApi } from '../api/projects';
import { Button } from '../components/ui/Button';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';
import { ProjectFormDialog } from '../components/projects/ProjectFormDialog';
import { cn, formatRelativeTime } from '../lib/utils';
import { AlertTriangle, FolderKanban, FolderPlus, Loader2, Pencil, Trash2 } from 'lucide-react';
import type { Project } from '../types/project';

export function ProjectsPage() {
  const navigate = useNavigate();
  const { data: projects, loading, error, refresh } = usePolling<Project[]>(
    () => projectsApi.list(),
    15000
  );
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const [confirmProject, setConfirmProject] = useState<Project | null>(null);
  const [busy, setBusy] = useState(false);

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };

  const openEdit = (project: Project) => {
    setEditing(project);
    setFormOpen(true);
  };

  const remove = async () => {
    if (!confirmProject) return;
    setBusy(true);
    try {
      await projectsApi.remove(confirmProject.id);
      setConfirmProject(null);
      refresh();
    } finally {
      setBusy(false);
    }
  };

  if (loading && !projects) {
    return (
      <div className="flex items-center justify-center h-64" role="status" aria-label="Carregando projetos">
        <Loader2 className="w-6 h-6 text-accent-primary animate-spin" />
      </div>
    );
  }

  if (error && !projects) {
    return (
      <div className="flex items-center justify-center h-64 text-center">
        <div>
          <AlertTriangle className="w-10 h-10 text-accent-secondary mx-auto mb-3" aria-hidden="true" />
          <h2 className="text-lg font-semibold text-primary">Falha ao carregar projetos</h2>
          <p className="text-sm text-secondary mt-1 font-mono">{error}</p>
          <button
            onClick={refresh}
            className="mt-4 px-4 py-2 bg-accent-primary text-white rounded-xl text-sm hover:bg-accent-secondary transition-colors focus-ring"
          >
            Tentar novamente
          </button>
        </div>
      </div>
    );
  }

  const list = projects ?? [];

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-primary tracking-tight">Projetos</h1>
          <p className="text-secondary mt-1">
            Organize seus projetos: tarefas, quadro Kanban e um workspace de arquivos
          </p>
        </div>
        <Button onClick={openCreate}>
          <FolderPlus className="w-4 h-4" aria-hidden="true" />
          Novo projeto
        </Button>
      </div>

      {list.length === 0 ? (
        <div className="rounded-[20px] border border-subtle bg-surface-container py-16 text-center">
          <FolderKanban className="w-12 h-12 text-muted mx-auto mb-3" aria-hidden="true" />
          <p className="text-secondary">Nenhum projeto ainda</p>
          <p className="text-sm text-muted mt-1">Crie seu primeiro projeto para começar</p>
          <Button className="mt-4" onClick={openCreate}>
            <FolderPlus className="w-4 h-4" aria-hidden="true" />
            Novo projeto
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {list.map((project) => {
            const progress = project.task_count > 0
              ? Math.round((project.done_count / project.task_count) * 100)
              : 0;
            return (
              <div
                key={project.id}
                role="button"
                tabIndex={0}
                onClick={() => navigate(`/projects/${project.id}`)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    navigate(`/projects/${project.id}`);
                  }
                }}
                className={cn(
                  'group rounded-[20px] border border-subtle bg-surface-base p-5 cursor-pointer',
                  'transition-colors hover:border-accent-primary/40 hover:bg-surface-elevated/40 focus-ring'
                )}
              >
                <div className="flex items-start gap-3">
                  <span
                    className="w-3 h-3 rounded-full flex-shrink-0 mt-1.5"
                    style={{ backgroundColor: project.color }}
                    aria-hidden="true"
                  />
                  <div className="min-w-0 flex-1">
                    <h2 className="text-base font-semibold text-primary truncate">
                      {project.name}
                    </h2>
                    <p className="text-sm text-secondary mt-1 line-clamp-2 min-h-[2.5rem]">
                      {project.description || 'Sem descrição'}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        openEdit(project);
                      }}
                      aria-label={`Editar ${project.name}`}
                      className="p-1.5 rounded-lg text-muted hover:text-primary hover:bg-surface-elevated focus-ring"
                    >
                      <Pencil className="w-3.5 h-3.5" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        setConfirmProject(project);
                      }}
                      aria-label={`Excluir ${project.name}`}
                      className="p-1.5 rounded-lg text-muted hover:text-red-400 hover:bg-red-400/10 focus-ring"
                    >
                      <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                    </button>
                  </div>
                </div>

                <div className="mt-4">
                  <div className="flex items-center justify-between text-xs text-muted font-mono mb-1.5">
                    <span>
                      {project.done_count}/{project.task_count} tarefas
                    </span>
                    <span>{progress}%</span>
                  </div>
                  <div
                    className="h-1.5 rounded-full bg-surface-elevated overflow-hidden"
                    role="progressbar"
                    aria-valuenow={progress}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`Progresso de ${project.name}`}
                  >
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${progress}%`, backgroundColor: project.color }}
                    />
                  </div>
                  <p className="text-[11px] text-muted mt-2 font-mono">
                    atualizado {formatRelativeTime(project.updated_at)}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <ProjectFormDialog
        open={formOpen}
        project={editing}
        onClose={() => setFormOpen(false)}
        onSaved={refresh}
      />

      <ConfirmDialog
        open={Boolean(confirmProject)}
        title="Excluir projeto"
        description={`"${confirmProject?.name ?? ''}", suas tarefas e todos os arquivos do workspace serão removidos permanentemente.`}
        confirmLabel="Excluir"
        busy={busy}
        onConfirm={remove}
        onClose={() => setConfirmProject(null)}
      />
    </div>
  );
}
