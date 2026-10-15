/**
 * Session storage for the web panel.
 *
 * After `POST /api/auth/login` the panel holds a signed, expiring *session*
 * token instead of the long-lived `ODIN_API_TOKEN`. This module owns where that
 * token lives (`localStorage`) and exposes the single credential getter used by
 * the REST client and the WebSocket hook.
 *
 * A pre-existing `localStorage['odin_api_token']` is still honoured as a
 * fallback so setups that were configured by hand keep working; it is simply
 * outranked by a valid session.
 */

const SESSION_KEY = 'odin_session';
export const LEGACY_TOKEN_KEY = 'odin_api_token';

/** Fired when the backend rejects the current credential (HTTP 401 / WS 1008). */
export const UNAUTHORIZED_EVENT = 'odin:unauthorized';

export interface StoredSession {
  token: string;
  /** Expiry as a Unix timestamp in milliseconds. */
  expiresAt: number;
}

/** The current session, or `null` when absent/expired (expired ones are pruned). */
export function getStoredSession(): StoredSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredSession | null;
    if (!parsed?.token || typeof parsed.expiresAt !== 'number') return null;
    if (parsed.expiresAt <= Date.now()) {
      window.localStorage.removeItem(SESSION_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

/** Persist a freshly issued session. `expiresAtSeconds` comes from the API. */
export function saveSession(token: string, expiresAtSeconds: number): StoredSession {
  const session: StoredSession = { token, expiresAt: expiresAtSeconds * 1000 };
  try {
    window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } catch {
    // Storage unavailable (private mode) — the app stays logged in for this tab
    // only, via the in-memory value returned below.
  }
  return session;
}

export function clearSession(): void {
  try {
    window.localStorage.removeItem(SESSION_KEY);
  } catch {
    // ignore
  }
}

/**
 * Credential to send on API/WebSocket requests: the session token when present,
 * otherwise the legacy raw API token.
 */
export function getAuthCredential(): string {
  const session = getStoredSession();
  if (session) return session.token;
  try {
    return window.localStorage.getItem(LEGACY_TOKEN_KEY) || '';
  } catch {
    return '';
  }
}

/** Tell the app the credential was rejected so it can return to the login screen. */
export function notifyUnauthorized(): void {
  window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
}
