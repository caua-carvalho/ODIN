import { View } from 'react-native';
import { cn } from '../../lib/utils';

export function ProgressBar({ percent, className }: { percent: number; className?: string }) {
  const clamped = Math.max(0, Math.min(100, percent));
  return (
    <View className={cn('h-1.5 rounded-full bg-surface-elevated overflow-hidden', className)}>
      <View className="h-full rounded-full bg-accent" style={{ width: `${clamped}%` }} />
    </View>
  );
}