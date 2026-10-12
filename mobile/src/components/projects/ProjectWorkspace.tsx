import { useState } from 'react';
import { View, Text, FlatList, Pressable, RefreshControl, ActivityIndicator } from 'react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as DocumentPicker from 'expo-document-picker';
import { File, Directory, Paths } from 'expo-file-system';
import * as Sharing from 'expo-sharing';
import {
  Folder,
  FolderOpen,
  File as FileIcon,
  Upload,
  FolderPlus,
  Trash2,
  ChevronRight,
} from 'lucide-react-native';

import { projectsApi } from '../../api/projects';
import { absoluteUrl, getClientConfig } from '../../lib/config';
import { PromptDialog } from '../ui/PromptDialog';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { Button } from '../ui/Button';
import { EmptyState } from '../ui/EmptyState';
import { formatBytes, formatRelativeTime } from '../../lib/format';
import type { ProjectFile } from '../../types/project';

interface ProjectWorkspaceProps {
  projectId: string;
}

function guessMime(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() ?? '';
  const map: Record<string, string> = {
    pdf: 'application/pdf',
    txt: 'text/plain',
    md: 'text/markdown',
    json: 'application/json',
    png: 'image/png',
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    gif: 'image/gif',
    webp: 'image/webp',
    svg: 'image/svg+xml',
    zip: 'application/zip',
    py: 'text/x-python',
    ts: 'text/typescript',
    tsx: 'text/typescript',
    js: 'text/javascript',
  };
  return map[ext] ?? 'application/octet-stream';
}

export function ProjectWorkspace({ projectId }: ProjectWorkspaceProps) {
  const queryClient = useQueryClient();
  const [currentPath, setCurrentPath] = useState('');
  const [mkdirOpen, setMkdirOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<ProjectFile | null>(null);
  const [busyFile, setBusyFile] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['files', projectId] });
  };

  const files = useQuery({
    queryKey: ['files', projectId, currentPath],
    queryFn: () => projectsApi.listFiles(projectId, currentPath),
  });

  const mkdirMutation = useMutation({
    mutationFn: (name: string) =>
      projectsApi.makeDirectory(
        projectId,
        currentPath ? `${currentPath}/${name}` : name
      ),
    onSuccess: () => {
      setMkdirOpen(false);
      invalidate();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (entry: ProjectFile) => projectsApi.deleteFile(projectId, entry.path),
    onSuccess: () => {
      setDeleteTarget(null);
      invalidate();
    },
  });

  const handleUpload = async () => {
    setActionError(null);
    try {
      const result = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true });
      const asset = result.assets?.[0];
      if (result.canceled || !asset) return;
      await projectsApi.uploadFile(projectId, { uri: asset.uri, name: asset.name, type: asset.mimeType }, currentPath);
      invalidate();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleDownload = async (entry: ProjectFile) => {
    setActionError(null);
    setBusyFile(entry.path);
    try {
      const dir = new Directory(Paths.cache, 'odin-files');
      if (!dir.exists) dir.create();
      const token = getClientConfig()?.token;
      const url = absoluteUrl(projectsApi.downloadUrl(projectId, entry.path));
      const file = await File.downloadFileAsync(url, dir, {
        idempotent: true,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      const available = await Sharing.isAvailableAsync();
      if (available) {
        await Sharing.shareAsync(file.uri, {
          mimeType: guessMime(entry.name),
          dialogTitle: entry.name,
        });
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyFile(null);
    }
  };

  const openDir = (entry: ProjectFile) => {
    if (entry.is_dir) setCurrentPath(entry.path);
  };

  const breadcrumbs = currentPath ? currentPath.split('/') : [];

  const navigateTo = (index: number) => {
    if (index < 0) setCurrentPath('');
    else setCurrentPath(breadcrumbs.slice(0, index + 1).join('/'));
  };

  return (
    <View className="flex-1 gap-3">
      {/* Breadcrumb + actions */}
      <View className="px-1 gap-2">
        <ScrollBreadcrumb crumbs={breadcrumbs} onNavigate={navigateTo} />
        <View className="flex-row gap-2">
          <Button size="sm" variant="subtle" className="flex-1" onPress={() => void handleUpload()}>
            <Upload size={14} color="#F5F5F7" />
            <Text className="text-xs font-medium text-primary">Enviar</Text>
          </Button>
          <Button size="sm" variant="subtle" className="flex-1" onPress={() => setMkdirOpen(true)}>
            <FolderPlus size={14} color="#F5F5F7" />
            <Text className="text-xs font-medium text-primary">Pasta</Text>
          </Button>
        </View>
      </View>

      {actionError ? (
        <View className="rounded-xl border border-err/20 bg-err/5 px-3 py-2">
          <Text className="text-[11px] font-mono text-err">{actionError}</Text>
        </View>
      ) : null}

      {files.isLoading ? (
        <View className="items-center py-10">
          <ActivityIndicator size="small" color="#FF7A00" />
        </View>
      ) : files.isError ? (
        <EmptyState title="Falha ao listar arquivos" hint={String(files.error?.message ?? '')} />
      ) : (files.data?.entries ?? []).length === 0 ? (
        <EmptyState
          icon={<FolderOpen size={28} color="#6E6E73" />}
          title="Pasta vazia"
          hint="Envie arquivos ou crie uma pasta"
        />
      ) : (
        <FlatList
          data={files.data!.entries}
          keyExtractor={(e) => e.path}
          className="flex-1"
          contentContainerStyle={{ gap: 8, paddingBottom: 16 }}
          refreshControl={
            <RefreshControl refreshing={files.isRefetching} onRefresh={() => void files.refetch()} tintColor="#FF7A00" />
          }
          ItemSeparatorComponent={() => <View className="h-0.5" />}
          renderItem={({ item }) => (
            <Pressable
              onPress={() => (item.is_dir ? openDir(item) : void handleDownload(item))}
              className="bg-surface-base border border-line rounded-xl px-3.5 py-3 flex-row items-center gap-3 active:bg-surface-container"
              accessibilityLabel={item.is_dir ? `Abrir pasta ${item.name}` : `Baixar arquivo ${item.name}`}
            >
              {item.is_dir ? (
                <Folder size={18} color="#FF9A3D" />
              ) : (
                <FileIcon size={18} color="#A1A1A6" />
              )}
              <View className="flex-1 gap-0.5">
                <Text className="text-sm text-primary font-medium" numberOfLines={1}>
                  {item.name}
                </Text>
                <Text className="font-mono text-[10px] text-muted">
                  {item.is_dir
                    ? formatRelativeTime(item.modified_at)
                    : `${formatBytes(item.size)} · ${formatRelativeTime(item.modified_at)}`}
                </Text>
              </View>
              {busyFile === item.path ? (
                <ActivityIndicator size="small" color="#FF7A00" />
              ) : item.is_dir ? (
                <ChevronRight size={16} color="#3a3a40" />
              ) : null}
              <Pressable onPress={() => setDeleteTarget(item)} hitSlop={10} className="p-2" accessibilityLabel={`Excluir ${item.name}`}>
                <Trash2 size={15} color="#6E6E73" />
              </Pressable>
            </Pressable>
          )}
        />
      )}

      <PromptDialog
        open={mkdirOpen}
        title="Nova pasta"
        placeholder="Nome da pasta"
        confirmLabel="Criar"
        busy={mkdirMutation.isPending}
        onConfirm={(name) => mkdirMutation.mutate(name)}
        onClose={() => setMkdirOpen(false)}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Excluir item?"
        description={
          deleteTarget
            ? deleteTarget.is_dir
              ? `A pasta "${deleteTarget.name}" e todo o seu conteúdo serão removidos.`
              : `O arquivo "${deleteTarget.name}" será removido.`
            : ''
        }
        confirmLabel="Excluir"
        danger
        busy={deleteMutation.isPending}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
      />
    </View>
  );
}

function ScrollBreadcrumb({
  crumbs,
  onNavigate,
}: {
  crumbs: string[];
  onNavigate: (index: number) => void;
}) {
  return (
    <View className="flex-row items-center flex-wrap">
      <Pressable onPress={() => onNavigate(-1)} hitSlop={8}>
        <Text className={crumbs.length === 0 ? 'font-mono text-xs text-primary' : 'font-mono text-xs text-muted'}>
          raiz
        </Text>
      </Pressable>
      {crumbs.map((crumb, index) => (
        <View key={`${crumb}-${index}`} className="flex-row items-center">
          <ChevronRight size={12} color="#3a3a40" />
          <Pressable onPress={() => onNavigate(index)} hitSlop={8}>
            <Text
              numberOfLines={1}
              className={
                index === crumbs.length - 1
                  ? 'font-mono text-xs text-primary max-w-[140px]'
                  : 'font-mono text-xs text-muted max-w-[120px]'
              }
            >
              {crumb}
            </Text>
          </Pressable>
        </View>
      ))}
    </View>
  );
}