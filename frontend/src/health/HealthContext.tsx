import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useLocation } from 'react-router-dom';
import { healthApi } from '../api/health';
import type { HealthResponse } from '../types/health';

/**
 * Routes whose pages actually render `/api/health` data (Dashboard, System,
 * Permissions). Only while one of these is on screen does the shared poll keep
 * hitting the endpoint — on every other screen (Chat, Projects, Tools, Skills)
 * the last snapshot is reused instead of consuming the API in the background.
 */
const POLLING_ROUTES = new Set(['/', '/system', '/permissions']);

/** Refresh cadence while a health-rendering route is visible. */
export const HEALTH_POLL_INTERVAL_MS = 15000;

interface HealthContextValue {
  data: HealthResponse | null;
  loading: boolean;
  error: string | null;
  /** Force an immediate (deduplicated) refresh. */
  refresh: () => void;
}

const HealthContext = createContext<HealthContextValue | null>(null);

export function HealthProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const shouldPoll = POLLING_ROUTES.has(location.pathname);

  const [data, setData] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fetchingRef = useRef(false);
  const aliveRef = useRef(true);

  const fetchHealth = useCallback(async () => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    try {
      const result = await healthApi.getHealth();
      if (aliveRef.current) {
        setData(result);
        setError(null);
        setLoading(false);
      }
    } catch (err) {
      if (aliveRef.current) {
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      }
    } finally {
      fetchingRef.current = false;
    }
  }, []);

  // One snapshot on mount so the layout (sidebar/top bar) has something to show.
  useEffect(() => {
    aliveRef.current = true;
    void fetchHealth();
    return () => {
      aliveRef.current = false;
    };
  }, [fetchHealth]);

  // Continuous consumption only while a route that renders health is visible.
  useEffect(() => {
    if (!shouldPoll) return;
    void fetchHealth();
    const interval = setInterval(() => void fetchHealth(), HEALTH_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [shouldPoll, fetchHealth]);

  const value = useMemo<HealthContextValue>(
    () => ({ data, loading, error, refresh: fetchHealth }),
    [data, loading, error, fetchHealth]
  );

  return <HealthContext.Provider value={value}>{children}</HealthContext.Provider>;
}

export function useHealth(): HealthContextValue {
  const ctx = useContext(HealthContext);
  if (!ctx) throw new Error('useHealth must be used within a HealthProvider');
  return ctx;
}
