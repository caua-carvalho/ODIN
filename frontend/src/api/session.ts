/**
 * Session storage for the web panel.
 *
 * After `POST /api/auth/login` the panel holds a signed, expiring *session*
 * token instead of the long-lived `ODIN_API_TOKEN`. This module owns where that
 * token lives (`localStorage`) and exposes the single credential getter used by
 * the REST client and the WebSocket hook.
 *
 * Legacy raw-token migration (issue #15): older installs stored the long-lived
 * `ODIN_API_TOKEN` directly in `localStorage['odin_api_token']`. That key is
 * still read here for a one-time, backward-compatible transition, but it is
 * **deprecated**: `AuthProvider` exchanges it for a session on boot and then
 * deletes it (`getLegacyToken`/`clearLegacyToken`), and a rejected credential
 * drops it too. New code must never write it; the long-lived secret should not
 * persist in the browser.
 */

const SESSION_KEY = 'odin_session';

/** @deprecated Legacy raw-token key, kept only for the one-time migration. */
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
 * A hand-set legacy raw API token, if any (used only for the one-time
 * migration to a session; see `AuthProvider`).
 */
export function getLegacyToken(): string | null {
  try {
    return window.localStorage.getItem(LEGACY_TOKEN_KEY) || null;
  } catch {
    return null;
  }
}

/** Drop the deprecated raw-token entry for good. */
export function clearLegacyToken(): void {
  try {
    window.localStorage.removeItem(LEGACY_TOKEN_KEY);
  } catch {
    // ignore
  }
}

/**
 * Credential to send on API/WebSocket requests: the session token when present,
 * otherwise the legacy raw API token (until `AuthProvider` migrates or drops
 * it). Never returns both.
 */
export function getAuthCredential(): string {
  const session = getStoredSession();
  if (session) return session.token;
  return getLegacyToken() || '';
}

/** Tell the app the credential was rejected so it can return to the login screen. */
export function notifyUnauthorized(): void {
  window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
}
