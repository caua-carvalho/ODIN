import { useState, type FormEvent } from 'react';
import { Lock } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { useAuth } from '../auth/AuthContext';
import { ApiError } from '../api/client';

/**
 * Login screen shown when the backend requires `ODIN_API_TOKEN`.
 *
 * The raw token is only used here (sent in the login body); the panel keeps the
 * signed session token returned by the API, not the long-lived secret.
 */
export function LoginPage() {
  const { login } = useAuth();
  const [token, setToken] = useState('');
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (loading) return;

    const value = token.trim();
    if (!value) {
      setError('Enter your API token.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await login(value, remember);
      // On success the auth gate unmounts this page; no state reset needed.
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError('Invalid token. Check it and try again.');
      } else if (err instanceof ApiError && err.status === 429) {
        setError('Too many attempts. Wait a minute and try again.');
      } else if (err instanceof ApiError && err.status === 503) {
        setError('Login is not enabled on this server.');
      } else {
        setError('Could not reach the server. Is Odin running?');
      }
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface-canvas flex items-center justify-center p-4">
      <div className="w-full max-w-sm animate-page-in">
        <div className="flex flex-col items-center gap-1.5 mb-6">
          <span className="font-mono text-3xl font-bold text-primary tracking-tight select-none">
            ODIN
          </span>
          <span className="text-[10px] text-muted uppercase tracking-widest">
            Personal AI Assistant
          </span>
        </div>

        <Card className="p-6">
          <form onSubmit={handleSubmit} noValidate className="space-y-5">
            <div className="flex items-center gap-3">
              <span className="flex items-center justify-center w-9 h-9 rounded-xl bg-surface-elevated border border-subtle text-accent-primary shrink-0">
                <Lock size={16} aria-hidden="true" />
              </span>
              <div className="min-w-0">
                <h1 className="text-sm font-semibold text-primary">Sign in</h1>
                <p className="text-xs text-secondary">Enter your API token to continue.</p>
              </div>
            </div>

            <Input
              label="API token"
              type="password"
              name="token"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder="••••••••••••"
              autoFocus
              autoComplete="current-password"
              spellCheck={false}
              disabled={loading}
              error={error ?? undefined}
            />

            <label className="flex items-center gap-2 text-sm text-secondary select-none cursor-pointer">
              <input
                type="checkbox"
                checked={remember}
                onChange={(event) => setRemember(event.target.checked)}
                disabled={loading}
                className="h-4 w-4 rounded border border-subtle bg-surface-elevated"
                style={{ accentColor: 'var(--color-accent-primary)' }}
              />
              Keep me signed in for 7 days
            </label>

            <Button type="submit" className="w-full" loading={loading}>
              {loading ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>
        </Card>

        <p className="mt-4 text-center text-[11px] text-muted leading-relaxed">
          The token is <span className="font-mono">ODIN_API_TOKEN</span> from the
          server&apos;s <span className="font-mono">.env</span>.
        </p>
      </div>
    </div>
  );
}
