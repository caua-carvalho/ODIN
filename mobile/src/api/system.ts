import { api } from './client';
import type { SystemInfo } from '../types/system';

export const systemApi = {
  getSystemInfo: () => api.get<SystemInfo>('/api/system'),
};