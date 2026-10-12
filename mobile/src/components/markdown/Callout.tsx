import type { ComponentType, ReactNode } from 'react';
import { Text, View } from 'react-native';
import {
  Info,
  Lightbulb,
  AlertCircle,
  AlertTriangle,
  AlertOctagon,
} from 'lucide-react-native';
import { cn } from '../../lib/utils';

interface CalloutStyle {
  icon: ComponentType<{ size?: number; color?: string }>;
  label: string;
  container: string;
  accent: string;
  iconColor: string;
}

/** ODIN palette for GitHub alert callouts, mirroring the web console. */
const STYLES: Record<string, CalloutStyle> = {
  note: {
    icon: Info,
    label: 'Nota',
    container: 'border-accent-subtle/25 bg-accent-subtle/5',
    accent: 'text-accent-subtle',
    iconColor: '#00D9FF',
  },
  tip: {
    icon: Lightbulb,
    label: 'Dica',
    container: 'border-ok/25 bg-ok/5',
    accent: 'text-ok',
    iconColor: '#34d399',
  },
  important: {
    icon: AlertCircle,
    label: 'Importante',
    container: 'border-accent/30 bg-accent/5',
    accent: 'text-accent',
    iconColor: '#FF7A00',
  },
  warning: {
    icon: AlertTriangle,
    label: 'Aviso',
    container: 'border-warn/30 bg-warn/5',
    accent: 'text-warn',
    iconColor: '#fbbf24',
  },
  caution: {
    icon: AlertOctagon,
    label: 'Cuidado',
    container: 'border-err/30 bg-err/5',
    accent: 'text-err',
    iconColor: '#f87171',
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
    <View
      className={cn('my-3 rounded-xl border px-4 py-3', style.container)}
      accessibilityLabel={style.label}
    >
      <View className="mb-1 flex-row items-center gap-1.5">
        <Icon size={14} color={style.iconColor} />
        <Text className={cn('text-[11px] font-semibold uppercase tracking-wider', style.accent)}>
          {style.label}
        </Text>
      </View>
      <View>{children}</View>
    </View>
  );
}
