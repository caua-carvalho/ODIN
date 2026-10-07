import { useEffect, useRef, useState, useCallback } from 'react';

interface UsePollingResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

/**
 * Generic polling hook with deduplication and controlled refresh.
 * Uses a single interval and avoids overlapping requests.
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
  immediate = true
): UsePollingResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(immediate);
  const [error, setError] = useState<string | null>(null);
  const fetchingRef = useRef(false);
  const fetcherRef = useRef(fetcher);
  const aliveRef = useRef(true);

  fetcherRef.current = fetcher;

  const doFetch = useCallback(async () => {
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    try {
      const result = await fetcherRef.current();
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

  const refresh = useCallback(() => {
    void doFetch();
  }, [doFetch]);

  useEffect(() => {
    aliveRef.current = true;
    if (immediate) void doFetch();
    const interval = setInterval(() => void doFetch(), intervalMs);
    return () => {
      aliveRef.current = false;
      clearInterval(interval);
    };
  }, [intervalMs, immediate, doFetch]);

  return { data, loading, error, refresh };
}
