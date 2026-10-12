import { useEffect, useRef, useState } from 'react';
import { Dialog } from '../ui/Dialog';
import { Button } from '../ui/Button';
import { Input, Textarea } from '../ui/Input';
import { projectsApi } from '../../api/projects';
import { PROJECT_COLORS, type Project } from '../../types/project';
import { cn } from '../../lib/utils';

interface ProjectFormDialogProps {
  open: boolean;
  project?: Project | null;
  onClose: () => void;
  onSaved: (project: Project) => void;
}

export function ProjectFormDialog({ open, project, onClose, onSaved }: ProjectFormDialogProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [color, setColor] = useState(PROJECT_COLORS[0]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  const isEditing = Boolean(project);

  useEffect(() => {
    if (!open) return;
    setName(project?.name ?? '');
    setDescription(project?.description ?? '');
    setColor(project?.color ?? PROJECT_COLORS[0]);
    setError(null);
  }, [open, project]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setError('Informe um nome para o projeto.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = project
        ? await projectsApi.update(project.id, { name: name.trim(), description, color })
        : await projectsApi.create({ name: name.trim(), description, color });
      onSaved(saved);
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
      labelledBy="project-form-title"
      initialFocusRef={nameRef}
      className="max-w-lg"
    >
      <form onSubmit={handleSubmit} className="p-5 space-y-4">
        <div>
          <h2 id="project-form-title" className="text-base font-semibold text-primary">
            {isEditing ? 'Editar projeto' : 'Novo projeto'}
          </h2>
          <p className="text-sm text-secondary mt-1">
            Cada projeto tem lista de tarefas, quadro Kanban e um workspace de arquivos.
          </p>
        </div>

        <Input
          ref={nameRef}
          label="Nome"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Ex.: Site pessoal"
          maxLength={255}
          error={error ?? undefined}
        />

        <Textarea
          label="Descrição"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Opcional"
          rows={3}
        />

        <div>
          <span className="block text-sm font-medium text-secondary mb-1.5">Cor</span>
          <div className="flex items-center gap-2 flex-wrap">
            {PROJECT_COLORS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setColor(option)}
                aria-label={`Cor ${option}`}
                aria-pressed={color === option}
                className={cn(
                  'w-7 h-7 rounded-full border-2 transition-transform focus-ring',
                  color === option ? 'border-primary scale-110' : 'border-transparent'
                )}
                style={{ backgroundColor: option }}
              />
            ))}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 pt-1">
          <Button type="button" variant="ghost" size="sm" onClick={onClose} disabled={saving}>
            Cancelar
          </Button>
          <Button type="submit" size="sm" loading={saving}>
            {isEditing ? 'Salvar' : 'Criar projeto'}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
