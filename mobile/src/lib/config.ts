import AsyncStorage from '@react-native-async-storage/async-storage';

export interface ServerConfig {
  /** Base URL of the Odin backend, e.g. http://192.168.0.10:8000 */
  url: string;
  /** Optional bearer token (enable ODIN_API_TOKEN on the backend). */
  token: string;
}

const STORAGE_KEY = 'odin.serverConfig.v1';

/**
 * Module-level cache of the active server config. The API client and the
 * WebSocket helper read from here synchronously, so there is no async drift
 * between "the config the user sees" and "the config requests use".
 */
let cached: ServerConfig | null = null;

export async function loadStoredConfig(): Promise<ServerConfig | null> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ServerConfig;
    if (!parsed || typeof parsed.url !== 'string' || !parsed.url.trim()) return null;
    cached = normalize(parsed);
    return cached;
  } catch {
    return null;
  }
}

export async function saveConfig(config: ServerConfig): Promise<ServerConfig> {
  const next = normalize(config);
  cached = next;
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  return next;
}

export async function clearConfig(): Promise<void> {
  cached = null;
  await AsyncStorage.removeItem(STORAGE_KEY);
}

export function getClientConfig(): ServerConfig | null {
  return cached;
}

function normalize(config: ServerConfig): ServerConfig {
  return {
    url: config.url.trim().replace(/\/+$/, ''),
    token: (config.token ?? '').trim(),
  };
}

/** Absolute URL for a relative /api endpoint. */
export function absoluteUrl(endpoint: string): string {
  const url = cached?.url ?? '';
  return `${url}${endpoint}`;
}

/** WebSocket URL for a conversation, including the auth token when set. */
export function wsUrl(conversationId: string): string {
  const cfg = cached;
  if (!cfg?.url) return '';
  const base = cfg.url.replace(/\/+$/, '');
  const protocol = base.startsWith('https') ? 'wss' : 'ws';
  const host = base.replace(/^https?:\/\//, '');
  const tokenParam = cfg.token ? `?token=${encodeURIComponent(cfg.token)}` : '';
  return `${protocol}://${host}/api/ws/${conversationId}${tokenParam}`;
}