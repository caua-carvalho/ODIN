import { api } from './client';
import type { PermissionRequest, PermissionActionResponse } from '../types/permission';

export const permissionsApi = {
  listPermissions: (status?: string, limit = 100) => {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    params.set('limit', String(limit));
    return api.get<PermissionRequest[]>(`/api/permissions?${params.toString()}`);
  },
  listPendingPermissions: () => api.get<PermissionRequest[]>('/api/permissions/pending'),
  approvePermission: (id: string) => api.post<PermissionActionResponse>(`/api/permissions/${id}/approve`, {}),
  denyPermission: (id: string) => api.post<PermissionActionResponse>(`/api/permissions/${id}/deny`, {}),
};