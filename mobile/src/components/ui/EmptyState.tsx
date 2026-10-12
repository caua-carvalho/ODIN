import { View, Text } from 'react-native';
import { cn } from '../../lib/utils';

export function EmptyState({
  icon,
  title,
  hint,
  className,
}: {
  icon?: React.ReactNode;
  title: string;
  hint?: string;
  className?: string;
}) {
  return (
    <View className={cn('items-center justify-center py-10 px-6 gap-2', className)}>
      {icon}
      <Text className="text-sm font-medium text-secondary text-center">{title}</Text>
      {hint ? <Text className="text-xs text-muted text-center">{hint}</Text> : null}
    </View>
  );
}