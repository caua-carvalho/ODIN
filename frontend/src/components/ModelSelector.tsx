import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, Loader2, AlertTriangle, Cpu } from 'lucide-react';
import { cn } from '../lib/utils';
import { providersApi } from '../api/providers';
import type { ProvidersResponse } from '../types/provider';

interface ModelSelectorProps {
  /** Current provider id reported by /api/health (initial label). */
  provider: string;
  /** Current model reported by /api/health (initial label). */
  model: string;
  /** Called after a successful switch so the layout can refresh health. */
  onChanged?: () => void;
  className?: string;
}

/**
 * Provider + model dropdown for the top telemetry bar.
 *
 * The catalog is fetched lazily when the menu opens (Gemini model discovery can
 * take a moment); the button label always reflects the latest active selection.
 */
export function ModelSelector({ provider, model, onChanged, className }: ModelSelectorProps) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<ProvidersResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [switching, setSwitching] = useState<{ provider: string; model: string } | null>(null);
  const [switchError, setSwitchError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const active = data?.active ?? { provider, model };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await providersApi.list());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const handleToggle = () => {
    setOpen((prev) => {
      const next = !prev;
      if (next && !data && !loading) void load();
      return next;
    });
  };

  // Close on Escape or when clicking outside the widget.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const handleSelect = async (p: string, m: string) => {
    if (p === active.provider && m === active.model) {
      setOpen(false);
      return;
    }
    setSwitching({ provider: p, model: m });
    setSwitchError(null);
    try {
      const result = await providersApi.select(p, m);
      setData((prev) => (prev ? { ...prev, active: result } : prev));
      setOpen(false);
      onChanged?.();
    } catch (err) {
      setSwitchError(err instanceof Error ? err.message : String(err));
    } finally {
      setSwitching(null);
    }
  };

  return (
    <div ref={rootRef} className={cn('relative', className)}>
      <button
        onClick={handleToggle}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Select model provider"
        title="Change provider or model"
        className="flex items-center gap-1.5 px-2 py-1 rounded-lg border border-transparent hover:border-subtle hover:bg-surface-elevated text-xs text-secondary transition-colors focus-ring"
      >
        <Cpu className="w-3.5 h-3.5 text-muted" aria-hidden="true" />
        <span className="font-mono text-primary truncate max-w-[100px]">{active.provider}</span>
        <span className="text-muted">/</span>
        <span className="font-mono text-primary truncate max-w-[160px]">{active.model}</span>
        <ChevronDown
          className={cn('w-3.5 h-3.5 text-muted transition-transform', open && 'rotate-180')}
          aria-hidden="true"
        />
      </button>

      {open && (
        <div
          role="listbox"
          aria-label="Available models"
          className={cn(
            'absolute right-0 top-full mt-2 z-50 w-[min(22rem,calc(100vw-2rem))]',
            'bg-surface-elevated border border-subtle rounded-xl',
            'shadow-[0_8px_32px_rgba(0,0,0,0.4)] overflow-hidden'
          )}
        >
          <div className="px-4 py-2.5 border-b border-subtle">
            <p className="text-xs font-medium text-primary">Model</p>
            <p className="text-[11px] text-muted font-mono">
              {active.provider} / {active.model}
            </p>
          </div>

          {switchError && (
            <div
              className="mx-3 mt-2 px-3 py-2 rounded-lg bg-red-400/10 border border-red-400/20 text-xs text-red-400 flex items-start gap-2"
              role="alert"
            >
              <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" aria-hidden="true" />
              <span className="break-words">{switchError}</span>
            </div>
          )}

          <div className="max-h-[min(24rem,60vh)] overflow-y-auto scrollbar-thin py-1">
            {loading && (
              <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted" role="status">
                <Loader2 className="w-4 h-4 text-accent-primary animate-spin" aria-hidden="true" />
                Loading models…
              </div>
            )}

            {!loading && error && (
              <div className="p-4 text-xs text-red-400 font-mono" role="alert">
                {error}
              </div>
            )}

            {!loading && !error &&
              data?.providers.map((p) => {
                const isCurrentProvider = p.id === active.provider;
                return (
                  <div key={p.id} className="px-1 py-1">
                    <p className="px-3 pt-1.5 pb-1 text-[11px] uppercase tracking-wider text-muted flex items-center gap-2">
                      <span className="truncate">{p.label}</span>
                      {!p.configured && (
                        <span
                          className="uppercase tracking-normal text-[10px] text-amber-400 font-mono flex-shrink-0"
                          title="Add the API key to .env to enable this provider"
                        >
                          no key
                        </span>
                      )}
                    </p>
                    {p.models.length === 0 ? (
                      <p className="px-3 py-1.5 text-xs text-muted font-mono">
                        no models available
                      </p>
                    ) : (
                      <ul className="space-y-0.5">
                        {p.models.map((m) => {
                          const isActive = isCurrentProvider && m === active.model;
                          const pending =
                            switching?.provider === p.id && switching?.model === m;
                          return (
                            <li key={m}>
                              <button
                                role="option"
                                aria-selected={isActive}
                                disabled={!p.configured || switching !== null}
                                onClick={() => handleSelect(p.id, m)}
                                className={cn(
                                  'w-full flex items-center gap-2 px-3 py-1.5 text-left text-xs rounded-lg transition-colors focus-ring',
                                  isActive
                                    ? 'bg-accent-primary/10 text-primary'
                                    : 'text-secondary hover:bg-surface-container hover:text-primary',
                                  !p.configured && 'opacity-40 cursor-not-allowed'
                                )}
                              >
                                <span className="w-3.5 flex-shrink-0">
                                  {pending ? (
                                    <Loader2 className="w-3.5 h-3.5 text-accent-primary animate-spin" aria-hidden="true" />
                                  ) : isActive ? (
                                    <Check className="w-3.5 h-3.5 text-accent-primary" aria-hidden="true" />
                                  ) : null}
                                </span>
                                <span className="font-mono truncate">{m}</span>
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
}