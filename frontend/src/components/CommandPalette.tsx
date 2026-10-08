import { useEffect, useMemo, useRef, useState } from 'react';
import { CornerDownLeft, Search, type LucideIcon } from 'lucide-react';
import { Dialog } from './ui/Dialog';
import { cn } from '../lib/utils';

export interface PaletteAction {
  id: string;
  label: string;
  icon: LucideIcon;
  /** Shortcut hint rendered on the right (e.g. "Ctrl B"). */
  hint?: string;
  run: () => void;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  actions: PaletteAction[];
}

/**
 * ⌘K / Ctrl+K command palette.
 * Accessible combobox+listbox pattern: the input announces the focused option via
 * aria-activedescendant, and Arrow keys / Enter / Escape steer it like a select.
 */
export function CommandPalette({ open, onClose, actions }: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return actions;
    return actions.filter(
      (a) =>
        a.label.toLowerCase().includes(q) ||
        (a.hint ?? '').toLowerCase().includes(q)
    );
  }, [actions, query]);

  // Reset transient state every time the palette opens or the query changes.
  useEffect(() => {
    if (open) {
      setQuery('');
      setActive(0);
    }
  }, [open]);
  useEffect(() => setActive(0), [query]);

  const run = (action: PaletteAction) => {
    onClose();
    action.run();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === 'Home') {
      e.preventDefault();
      setActive(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      setActive(filtered.length - 1);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const action = filtered[active];
      if (action) run(action);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} initialFocusRef={inputRef} className="max-w-lg" label="Command palette">
      <div className="flex items-center gap-3 px-4 border-b border-subtle">
        <Search className="w-4 h-4 text-muted flex-shrink-0" aria-hidden="true" />
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a page or command…"
          role="combobox"
          aria-label="Search commands"
          aria-expanded="true"
          aria-controls="command-palette-list"
          aria-activedescendant={filtered[active] ? `cmd-item-${filtered[active].id}` : undefined}
          className="flex-1 bg-transparent py-4 text-sm text-primary placeholder-muted outline-none"
        />
        <kbd className="kbd hidden sm:inline-block">esc</kbd>
      </div>

      <ul
        id="command-palette-list"
        role="listbox"
        aria-label="Commands"
        className="py-2 max-h-80 overflow-y-auto scrollbar-thin"
      >
        {filtered.length === 0 && (
          <li className="px-4 py-3 text-sm text-muted" role="status">
            No commands match “{query}”
          </li>
        )}
        {filtered.map((action, i) => {
          const Icon = action.icon;
          const isActive = i === active;
          return (
            <li key={action.id}>
              <button
                id={`cmd-item-${action.id}`}
                role="option"
                aria-selected={isActive}
                tabIndex={-1}
                onClick={() => run(action)}
                onMouseEnter={() => setActive(i)}
                className={cn(
                  'w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm focus-ring',
                  isActive ? 'bg-surface-elevated text-primary' : 'text-secondary'
                )}
              >
                <Icon className="w-4 h-4 text-muted flex-shrink-0" aria-hidden="true" />
                <span className="font-medium truncate">{action.label}</span>
                {action.hint && (
                  <span className="ml-auto text-xs text-muted font-mono flex-shrink-0">{action.hint}</span>
                )}
                {isActive && (
                  <CornerDownLeft className="w-3.5 h-3.5 text-muted flex-shrink-0" aria-hidden="true" />
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </Dialog>
  );
}