import { api } from './client';
import type { ActiveSelection, ProvidersResponse } from '../types/provider';

export const providersApi = {
  list: () => api.get<ProvidersResponse>('/api/providers'),
  select: (provider: string, model: string) =>
    api.post<ActiveSelection>('/api/providers/select', { provider, model }),
};