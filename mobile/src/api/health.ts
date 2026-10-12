import { api } from './client';
import type { HealthResponse } from '../types/health';

export const healthApi = {
  getHealth: () => api.get<HealthResponse>('/api/health'),
};

/**
 * Probe a connection against an arbitrary URL/token *without* touching the
 * saved client config. Used by the connect/settings screens.
 */
export async function probeHealth(url: string, token?: string): Promise<HealthResponse> {
  const base = url.trim().replace(/\/+$/, '');
  const response = await fetch(`${base}/api/health`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }
  return response.json() as Promise<HealthResponse>;
}