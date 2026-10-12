import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { Dialog } from '../ui/Dialog';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { projectsApi } from '../../api/projects';
import { cn, formatBytes, formatRelativeTime } from '../../lib/utils';
import {
  ChevronRight,
  Download,
  File as FileIcon,
  FileText,
  Folder,
  FolderPlus,
  Image as ImageIcon,
  Loader2,
  Trash2,
  Upload,
} from 'lucide-react';
import type { ProjectFile } from '../../types/project';

interface WorkspaceFilesProps {
  projectId: string;
}

function fileIcon(entry: ProjectFile) {
  if (entry.is_dir) return Folder;
  const ext = entry.name.split('.').pop()?.toLowerCase() ?? '';
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'].includes(ext)) return ImageIcon;
  if (['txt', 'md', 'json', 'csv', 'yml', 'yaml', 'log', 'ts', 'tsx', 'js', 'py'].includes(ext))
    return FileText;
  return FileIcon;
}

export function WorkspaceFiles({ projectId }: WorkspaceFilesProps) {
  const [path, setPath] = useState('');
  const [entries, setEntries] = useState<ProjectFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [folderOpen, setFolderOpen] = useState(false);
  const [folderName, setFolderName] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirmEntry, setConfirmEntry] = useState<ProjectFile | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(
    async (target: string) => {
      setLoading(true);
      setError(null);
      try {
        const data = await projectsApi.listFiles(projectId, target);
        setEntries(data.entries);
        setPath(data.path);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    },
    [projectId]
  );

  useEffect(() => {
    void load('');
  }, [load]);

  const goUp = () => {
    if (!path) return;
    const parts = path.split('/');
    parts.pop();
    void load(parts.join('/'));
  };

  const uploadFiles = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (list.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      for (const file of list) {
        await projectsApi.uploadFile(projectId, file, path);
      }
      await load(path);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  };

  const createFolder = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!folderName.trim()) return;
    const target = path ? `${path}/${folderName.trim()}` : folderName.trim();
    setBusy(true);
    try {
      await projectsApi.makeDirectory(projectId, target);
      setFolderOpen(false);
      setFolderName('');
      await load(path);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!confirmEntry) return;
    setBusy(true);
    try {
      await projectsApi.deleteFile(projectId, confirmEntry.path);
      setConfirmEntry(null);
      await load(path);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const segments = path ? path.split('/') : [];

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <nav aria-label="Caminho do workspace" className="flex items-center gap-1 text-sm min-w-0">
          <button
            type="button"
            onClick={() => void load('')}
            className="text-secondary hover:text-primary font-mono focus-ring rounded px-1"
          >
            raiz
          </button>
          {segments.map((segment, index) => (
            <span key={index} className="flex items-center gap-1 min-w-0">
              <ChevronRight className="w-3.5 h-3.5 text-muted flex-shrink-0" aria-hidden="true" />
              <button
                type="button"
                onClick={() => void load(segments.slice(0, index + 1).join('/'))}
                className="text-secondary hover:text-primary font-mono truncate focus-ring rounded px-1"
              >
                {segment}
              </button>
            </span>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setFolderOpen(true)}
          >
            <FolderPlus className="w-4 h-4" aria-hidden="true" />
            Nova pasta
          </Button>
          <Button size="sm" loading={uploading} onClick={() => inputRef.current?.click()}>
            <Upload className="w-4 h-4" aria-hidden="true" />
            Enviar arquivo
          </Button>
          <input
            ref={inputRef}
            type="file"
            multiple
            className="hidden"
            onChange={(event) => {
              if (event.target.files) void uploadFiles(event.target.files);
              event.target.value = '';
            }}
          />
        </div>
      </div>

      {error && (
        <p
          className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-3 py-2"
          role="alert"
        >
          {error}
        </p>
      )}

      {/* Drop zone / listing */}
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          if (event.dataTransfer.files.length) void uploadFiles(event.dataTransfer.files);
        }}
        className={cn(
          'rounded-[20px] border bg-surface-container min-h-[280px] transition-colors',
          dragging ? 'border-accent-primary/60 bg-accent-primary/5' : 'border-subtle'
        )}
      >
        {loading ? (
          <div className="flex items-center justify-center h-64" role="status" aria-label="Carregando arquivos">
            <Loader2 className="w-6 h-6 text-accent-primary animate-spin" />
          </div>
        ) : entries.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-center px-4">
            <Upload className="w-10 h-10 text-muted mb-3" aria-hidden="true" />
            <p className="text-secondary">Nenhum arquivo neste local</p>
            <p className="text-sm text-muted mt-1">
              Arraste arquivos aqui ou use "Enviar arquivo"
            </p>
          </div>
        ) : (
          <ul className="divide-y divide-border-subtle">
            {path && (
              <li>
                <button
                  type="button"
                  onClick={goUp}
                  className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-surface-elevated/40 transition-colors focus-ring"
                >
                  <Folder className="w-4 h-4 text-accent-subtle" aria-hidden="true" />
                  <span className="text-sm text-secondary">..</span>
                </button>
              </li>
            )}
            {entries.map((entry) => {
              const Icon = fileIcon(entry);
              return (
                <li
                  key={entry.path}
                  className="group flex items-center gap-3 px-4 py-3 hover:bg-surface-elevated/40 transition-colors"
                >
                  <Icon
                    className={cn('w-4 h-4 flex-shrink-0', entry.is_dir ? 'text-accent-subtle' : 'text-muted')}
                    aria-hidden="true"
                  />
                  <button
                    type="button"
                    disabled={!entry.is_dir}
                    onClick={() => entry.is_dir && void load(entry.path)}
                    className={cn(
                      'min-w-0 flex-1 text-left rounded focus-ring',
                      entry.is_dir ? 'cursor-pointer' : 'cursor-default'
                    )}
                  >
                    <span className="block text-sm text-primary truncate">{entry.name}</span>
                    <span className="block text-xs text-muted font-mono">
                      {entry.is_dir ? 'pasta' : formatBytes(entry.size)} ·{' '}
                      {formatRelativeTime(entry.modified_at)}
                    </span>
                  </button>

                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
                    {!entry.is_dir && (
                      <a
                        href={projectsApi.downloadUrl(projectId, entry.path)}
                        download={entry.name}
                        aria-label={`Baixar ${entry.name}`}
                        className="p-1.5 rounded-lg text-muted hover:text-primary hover:bg-surface-elevated focus-ring"
                      >
                        <Download className="w-4 h-4" aria-hidden="true" />
                      </a>
                    )}
                    <button
                      type="button"
                      onClick={() => setConfirmEntry(entry)}
                      aria-label={`Excluir ${entry.name}`}
                      className="p-1.5 rounded-lg text-muted hover:text-red-400 hover:bg-red-400/10 focus-ring"
                    >
                      <Trash2 className="w-4 h-4" aria-hidden="true" />
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* New folder dialog */}
      <Dialog
        open={folderOpen}
        onClose={() => setFolderOpen(false)}
        labelledBy="new-folder-title"
        className="max-w-sm"
      >
        <form onSubmit={createFolder} className="p-5 space-y-4">
          <h2 id="new-folder-title" className="text-base font-semibold text-primary">
            Nova pasta
          </h2>
          <Input
            label="Nome"
            value={folderName}
            onChange={(event) => setFolderName(event.target.value)}
            placeholder="Ex.: documentos"
            autoFocus
          />
          <div className="flex items-center justify-end gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => setFolderOpen(false)} disabled={busy}>
              Cancelar
            </Button>
            <Button type="submit" size="sm" loading={busy} disabled={!folderName.trim()}>
              Criar
            </Button>
          </div>
        </form>
      </Dialog>

      <ConfirmDialog
        open={Boolean(confirmEntry)}
        title={confirmEntry?.is_dir ? 'Excluir pasta' : 'Excluir arquivo'}
        description={
          confirmEntry?.is_dir
            ? `"${confirmEntry.name}" e todo o seu conteúdo serão removidos.`
            : `"${confirmEntry?.name ?? ''}" será removido permanentemente.`
        }
        confirmLabel="Excluir"
        busy={busy}
        onConfirm={remove}
        onClose={() => setConfirmEntry(null)}
      />
    </div>
  );
}
