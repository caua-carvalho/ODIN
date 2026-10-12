import { Text, View } from 'react-native';
import { cn } from '../../lib/utils';

const RISK_STYLES: Record<string, { container: string; text: string; label: string }> = {
  low: { container: 'bg-ok/10 border-ok/20', text: 'text-ok', label: 'Baixo' },
  medium: { container: 'bg-warn/10 border-warn/20', text: 'text-warn', label: 'Médio' },
  high: { container: 'bg-err/10 border-err/20', text: 'text-err', label: 'Alto' },
  critical: { container: 'bg-err/20 border-err/40', text: 'text-err', label: 'Crítico' },
};

export function RiskBadge({ level }: { level: string }) {
  const style = RISK_STYLES[level] ?? RISK_STYLES.medium;
  return (
    <View className={cn('px-2 py-0.5 rounded-full border self-start', style.container)}>
      <Text className={cn('text-[10px] font-semibold uppercase tracking-wide', style.text)}>
        {style.label}
      </Text>
    </View>
  );
}

const STATUS_STYLES = {
  ok: { container: 'bg-ok/10 border-ok/20', text: 'text-ok' },
  err: { container: 'bg-err/10 border-err/20', text: 'text-err' },
  warn: { container: 'bg-warn/10 border-warn/20', text: 'text-warn' },
  neutral: { container: 'bg-surface-elevated border-line', text: 'text-secondary' },
} as const;

export function StatusBadge({
  status,
  label,
  className,
}: {
  status: keyof typeof STATUS_STYLES;
  label: string;
  className?: string;
}) {
  const style = STATUS_STYLES[status];
  return (
    <View className={cn('px-2 py-0.5 rounded-full border self-start', style.container, className)}>
      <Text className={cn('text-[10px] font-semibold uppercase tracking-wide', style.text)}>
        {label}
      </Text>
    </View>
  );
}