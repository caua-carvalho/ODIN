import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react';
import {
  loadStoredConfig,
  saveConfig,
  clearConfig,
  type ServerConfig,
} from '../lib/config';

interface ConfigContextValue {
  /** null when no server is configured yet (first run). */
  config: ServerConfig | null;
  loading: boolean;
  configure: (cfg: ServerConfig) => Promise<void>;
  reset: () => Promise<void>;
}

const ConfigContext = createContext<ConfigContextValue>({
  config: null,
  loading: true,
  configure: async () => {},
  reset: async () => {},
});

export function ConfigProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    loadStoredConfig().then((loaded) => {
      if (cancelled) return;
      setConfig(loaded);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const configure = useCallback(async (cfg: ServerConfig) => {
    const next = await saveConfig(cfg);
    setConfig(next);
  }, []);

  const reset = useCallback(async () => {
    await clearConfig();
    setConfig(null);
  }, []);

  return (
    <ConfigContext.Provider value={{ config, loading, configure, reset }}>
      {children}
    </ConfigContext.Provider>
  );
}

export function useServerConfig(): ConfigContextValue {
  return useContext(ConfigContext);
}