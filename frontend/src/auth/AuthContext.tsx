import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { ApiError } from '../api/client';
import { authApi } from '../api/auth';
import { healthApi } from '../api/health';
import {
  clearLegacyToken,
  clearSession,
  getAuthCredential,
  getLegacyToken,
  getStoredSession,
  saveSession,
  UNAUTHORIZED_EVENT,
} from '../api/session';

export type AuthStatus =
  | 'checking'
  | 'authenticated'
  | 'unauthenticated'
  | 'disabled';

interface AuthContextValue {
  status: AuthStatus;
  /** True when the backend has `ODIN_API_TOKEN` set (login is meaningful). */
  authEnabled: boolean;
  /** Exchange the API token for a session; resolves once logged in. */
  login: (token: string, remember: boolean) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/**
 * One-time transition for installs that stored the raw `ODIN_API_TOKEN` in
 * `localStorage['odin_api_token']` (issue #15): exchange it for a signed,
 * expiring session and delete the long-lived secret. Best-effort — a network
 * failure keeps the raw token so the migration can retry on the next boot,
 * while an invalid credential (401) or a server with auth disabled (503) drops
 * it instead of leaving a dead secret behind.
 */
async function migrateLegacyToken(): Promise<void> {
  if (getStoredSession()) {
    // A session already outranks the legacy token — drop the raw secret.
    clearLegacyToken();
    return;
  }
  const legacy = getLegacyToken();
  if (!legacy) return;
  try {
    const result = await authApi.login(legacy, true);
    saveSession(result.token, result.expires_at);
    clearLegacyToken();
  } catch (err) {
    if (err instanceof ApiError && (err.status === 401 || err.status === 503)) {
      clearLegacyToken();
    }
  }
}

/**
 * Owns the login state of the web panel.
 *
 * On boot it asks `/api/health` whether authentication is enabled (that
 * endpoint is public on purpose). If it is, any stored credential is validated
 * against `/api/auth/session`; a rejected credential drops the user back to the
 * login screen, while a network failure keeps the shell rendered (which shows
 * OFFLINE) rather than locking the panel behind a login that cannot succeed.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('checking');
  const [authEnabled, setAuthEnabled] = useState(false);

  const bootstrap = useCallback(async () => {
    let authRequired: boolean;
    try {
      const health = await healthApi.getHealth();
      authRequired = health.auth_required === true;
    } catch {
      // Backend unreachable — render the shell (it already handles OFFLINE).
      setStatus('authenticated');
      return;
    }

    setAuthEnabled(authRequired);
    if (!authRequired) {
      setStatus('disabled');
      return;
    }

    // Exchange a legacy raw token for a session before the first request.
    await migrateLegacyToken();

    if (!getAuthCredential()) {
      setStatus('unauthenticated');
      return;
    }

    try {
      await authApi.session();
      setStatus('authenticated');
    } catch (err) {
      setStatus(
        err instanceof ApiError && err.status === 401
          ? 'unauthenticated'
          : 'authenticated'
      );
    }
  }, []);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  // A 401 on any request (session expired) or a 1008 WebSocket close sends the
  // user back to the login screen.
  useEffect(() => {
    const handleUnauthorized = () => {
      setAuthEnabled(true);
      setStatus('unauthenticated');
    };
    window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
  }, []);

  const login = useCallback(async (token: string, remember: boolean) => {
    const result = await authApi.login(token, remember);
    saveSession(result.token, result.expires_at);
    setAuthEnabled(true);
    setStatus('authenticated');
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setStatus('unauthenticated');
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ status, authEnabled, login, logout }),
    [status, authEnabled, login, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
