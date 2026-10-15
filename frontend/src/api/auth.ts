import { api } from './client';

export interface LoginResponse {
  /** Signed session token to send as `Authorization: Bearer <token>`. */
  token: string;
  /** Session expiry as a Unix timestamp in seconds. */
  expires_at: number;
  ttl_seconds: number;
}

export interface SessionResponse {
  authenticated: boolean;
  /** `session` for a signed session token, `token` for the raw API token. */
  method: 'session' | 'token';
  expires_at: number | null;
}

export const authApi = {
  /** Exchange the API token for an expiring session token. */
  login: (token: string, remember: boolean) =>
    api.post<LoginResponse>('/api/auth/login', { token, remember }),
  /** Validate the current credential (used to check a stored session on boot). */
  session: () => api.get<SessionResponse>('/api/auth/session'),
};
