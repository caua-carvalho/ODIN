import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

export interface ServerConfig {
  /** Base URL of the Odin backend, e.g. http://192.168.0.10:8000 */
  url: string;
  /** Optional bearer token (enable ODIN_API_TOKEN on the backend). */
  token: string;
}

/**
 * Key used in both SecureStore (native) and AsyncStorage (web fallback and
 * legacy storage). The token is a bearer credential, so on iOS/Android it must
 * live in the Keychain/Keystore via expo-secure-store — never plaintext.
 */
const STORAGE_KEY = 'odin.serverConfig.v1';

/** SecureStore is not available on web; fall back to AsyncStorage there. */
const canUseSecureStore = Platform.OS !== 'web';

/**
 * Module-level cache of the active server config. The API client and the
 * WebSocket helper read from here synchronously, so there is no async drift
 * between "the config the user sees" and "the config requests use".
 */
let cached: ServerConfig | null = null;

async function readRaw(): Promise<string | null> {
  if (canUseSecureStore) return SecureStore.getItemAsync(STORAGE_KEY);
  return AsyncStorage.getItem(STORAGE_KEY);
}

async function writeRaw(value: string): Promise<void> {
  if (canUseSecureStore) {
    await SecureStore.setItemAsync(STORAGE_KEY, value);
  } else {
    await AsyncStorage.setItem(STORAGE_KEY, value);
  }
}

async function removeRaw(): Promise<void> {
  if (canUseSecureStore) {
    await SecureStore.deleteItemAsync(STORAGE_KEY);
  }
  // Always clean the AsyncStorage copy too, so no plaintext token lingers.
  await AsyncStorage.removeItem(STORAGE_KEY);
}

/** Migrate a config previously stored in AsyncStorage into SecureStore. */
async function migrateLegacyConfig(): Promise<void> {
  if (!canUseSecureStore) return;
  try {
    const legacy = await AsyncStorage.getItem(STORAGE_KEY);
    if (!legacy) return;
    const parsed = JSON.parse(legacy) as ServerConfig;
    if (!parsed || typeof parsed.url !== 'string' || !parsed.url.trim()) return;
    await SecureStore.setItemAsync(STORAGE_KEY, JSON.stringify(normalize(parsed)));
    await AsyncStorage.removeItem(STORAGE_KEY);
  } catch {
    // Corrupt or unreadable legacy data — ignore, the user can reconfigure.
  }
}

export async function loadStoredConfig(): Promise<ServerConfig | null> {
  try {
    await migrateLegacyConfig();
    const raw = await readRaw();
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
  await writeRaw(JSON.stringify(next));
  cached = next;
  return next;
}

export async function clearConfig(): Promise<void> {
  cached = null;
  await removeRaw();
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