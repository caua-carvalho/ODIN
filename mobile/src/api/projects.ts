import { api, upload } from './client';
import type {
  FileList,
  Project,
  ProjectCreate,
  ProjectFile,
  ProjectUpdate,
  Task,
  TaskCreate,
  TaskReorderItem,
  TaskUpdate,
} from '../types/project';

export const projectsApi = {
  list: () => api.get<Project[]>('/api/projects'),
  create: (data: ProjectCreate) => api.post<Project>('/api/projects', data),
  get: (id: string) => api.get<Project>(`/api/projects/${id}`),
  update: (id: string, data: ProjectUpdate) => api.patch<Project>(`/api/projects/${id}`, data),
  remove: (id: string) => api.delete<{ deleted: string }>(`/api/projects/${id}`),

  listTasks: (projectId: string) => api.get<Task[]>(`/api/projects/${projectId}/tasks`),
  createTask: (projectId: string, data: TaskCreate) =>
    api.post<Task>(`/api/projects/${projectId}/tasks`, data),
  updateTask: (taskId: string, data: TaskUpdate) => api.patch<Task>(`/api/tasks/${taskId}`, data),
  deleteTask: (taskId: string) => api.delete<{ deleted: string }>(`/api/tasks/${taskId}`),
  reorderTasks: (projectId: string, tasks: TaskReorderItem[]) =>
    api.post<{ updated: number }>(`/api/projects/${projectId}/tasks/reorder`, { tasks }),

  listFiles: (projectId: string, path = '') =>
    api.get<FileList>(`/api/projects/${projectId}/files?path=${encodeURIComponent(path)}`),
  uploadFile: (projectId: string, file: { uri: string; name: string; type?: string }, path = '') => {
    const formData = new FormData();
    formData.append('file', file as unknown as Blob);
    formData.append('path', path);
    return upload<ProjectFile>(`/api/projects/${projectId}/files`, formData);
  },
  makeDirectory: (projectId: string, path: string) =>
    api.post<ProjectFile>(`/api/projects/${projectId}/files/mkdir`, { path }),
  deleteFile: (projectId: string, path: string) =>
    api.delete<{ deleted: string }>(
      `/api/projects/${projectId}/files?path=${encodeURIComponent(path)}`
    ),
  downloadUrl: (projectId: string, path: string) =>
    `/api/projects/${projectId}/files/download?path=${encodeURIComponent(path)}`,
};