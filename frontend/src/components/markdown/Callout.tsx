import type { ReactNode } from 'react';
import {
  Info,
  Lightbulb,
  AlertTriangle,
  AlertCircle,
  AlertOctagon,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '../../lib/utils';

interface CalloutStyle {
  icon: LucideIcon;
  label: string;
  container: string;
  accent: string;
}

const STYLES: Record<string, CalloutStyle> = {
  note: {
    icon: Info,
    label: 'Note',
    container: 'border-accent-subtle/25 bg-accent-subtle/[0.06]',
    accent: 'text-accent-subtle',
  },
  tip: {
    icon: Lightbulb,
    label: 'Tip',
    container: 'border-green-400/25 bg-green-400/[0.06]',
    accent: 'text-green-400',
  },
  important: {
    icon: AlertCircle,
    label: 'Important',
    container: 'border-accent-primary/30 bg-accent-primary/[0.07]',
    accent: 'text-accent-primary',
  },
  warning: {
    icon: AlertTriangle,
    label: 'Warning',
    container: 'border-accent-secondary/30 bg-accent-secondary/[0.07]',
    accent: 'text-accent-secondary',
  },
  caution: {
    icon: AlertOctagon,
    label: 'Caution',
    container: 'border-red-400/30 bg-red-400/[0.07]',
    accent: 'text-red-400',
  },
};

/**
 * GitHub-style alert block (`> [!NOTE] …`) rendered as a contained panel.
 * Content is passed through the markdown renderer by the parent.
 */
export function Callout({ type, children }: { type: string; children: ReactNode }) {
  const style = STYLES[type] ?? STYLES.note;
  const Icon = style.icon;

  return (
    <div
      className={cn('my-3 rounded-xl border px-4 py-3', style.container)}
      role="note"
      aria-label={style.label}
    >
      <div className={cn('mb-1 flex items-center gap-1.5', style.accent)}>
        <Icon size={14} aria-hidden="true" />
        <span className="text-[11px] font-medium uppercase tracking-wider">
          {style.label}
        </span>
      </div>
      <div className="odin-callout-body text-sm leading-relaxed text-secondary">
        {children}
      </div>
    </div>
  );
}
