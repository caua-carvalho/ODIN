import { api } from './client';
import type { HealthResponse } from '../types/health';

const TIMEOUT_MS = 8_000;

export const healthApi = {
  getHealth: () => api.get<HealthResponse>('/api/health'),
};

/**
 * Probe a connection against an arbitrary URL/token *without* touching the
 * saved client config. Used by the connect/settings screens.
 * Network/timeout failures are translated to pt-BR messages.
 */
export async function probeHealth(url: string, token?: string): Promise<HealthResponse> {
  const base = url.trim().replace(/\/+$/, '');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(`${base}/api/health`, {
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    return response.json() as Promise<HealthResponse>;
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new Error(
        'Tempo limite excedido. Verifique se o endereço está correto e se o backend está acessível.'
      );
    }
    if (err instanceof TypeError) {
      throw new Error(
        'Não foi possível conectar ao servidor. Verifique a URL, o IP da máquina e se o backend está rodando.'
      );
    }
    throw err;
  } finally {
    clearTimeout(timeout);
  }
}