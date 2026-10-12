import { X } from 'lucide-react';
import { Dialog } from './ui/Dialog';

interface ShortcutsHelpProps {
  open: boolean;
  onClose: () => void;
}

interface ShortcutRow {
  keys: string[];
  desc: string;
}

const GLOBAL_SHORTCUTS: ShortcutRow[] = [
  { keys: ['Ctrl', 'K'], desc: 'Open the command palette' },
  { keys: ['Ctrl', 'B'], desc: 'Toggle the navigation menu' },
  { keys: ['?'], desc: 'Show this shortcuts help' },
  { keys: ['1–7'], desc: 'Jump to Dashboard, Chat, Projects, Tools, Skills, Permissions or System' },
  { keys: ['Esc'], desc: 'Close menus, dialogs and the command palette' },
];

const CHAT_SHORTCUTS: ShortcutRow[] = [
  { keys: ['Enter'], desc: 'Send message' },
  { keys: ['Shift', 'Enter'], desc: 'Insert a new line' },
  { keys: ['Ctrl', 'Enter'], desc: 'Send message (alt.)' },
  { keys: ['Ctrl', '/'], desc: 'Focus the command input' },
  { keys: ['N'], desc: 'New conversation' },
  { keys: ['[', ']'], desc: 'Previous / next conversation' },
  { keys: ['R'], desc: 'Reload the conversation list' },
];

function ShortcutRow({ keys, desc }: ShortcutRow) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <span className="text-sm text-secondary">{desc}</span>
      <span className="flex items-center gap-1 flex-shrink-0">
        {keys.map((key) => (
          <kbd key={key} className="kbd">{key}</kbd>
        ))}
      </span>
    </div>
  );
}

export function ShortcutsHelp({ open, onClose }: ShortcutsHelpProps) {
  const titleId = 'shortcuts-help-title';

  return (
    <Dialog open={open} onClose={onClose} labelledBy={titleId} className="max-w-md">
      <div className="p-5">
        <div className="flex items-center justify-between gap-3">
          <h2 id={titleId} className="text-base font-semibold text-primary">
            Keyboard shortcuts
          </h2>
          <button
            onClick={onClose}
            aria-label="Close shortcuts help"
            className="text-muted hover:text-primary p-1 rounded-md focus-ring"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        </div>

        <h3 className="mt-4 text-xs uppercase tracking-widest text-muted">Global</h3>
        <div className="mt-1 divide-y divide-border-subtle">
          {GLOBAL_SHORTCUTS.map((row) => (
            <ShortcutRow key={row.desc} {...row} />
          ))}
        </div>

        <h3 className="mt-4 text-xs uppercase tracking-widest text-muted">Chat</h3>
        <div className="mt-1 divide-y divide-border-subtle">
          {CHAT_SHORTCUTS.map((row) => (
            <ShortcutRow key={row.desc} {...row} />
          ))}
        </div>

        <p className="mt-4 text-xs text-muted">
          Plain shortcuts are ignored while typing — only Ctrl/⌘ combos and Esc apply in text fields.
        </p>
      </div>
    </Dialog>
  );
}