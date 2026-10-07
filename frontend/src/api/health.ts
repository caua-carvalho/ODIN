import { api } from './client';
import type { HealthResponse } from '../types/health';

export const healthApi = {
  getHealth: () => api.get<HealthResponse>('/api/health'),
};