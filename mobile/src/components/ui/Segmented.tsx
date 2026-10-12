import { Pressable, Text, View } from 'react-native';
import { cn } from '../../lib/utils';

export interface SegmentOption<T extends string> {
  id: T;
  label: string;
}

interface SegmentedProps<T extends string> {
  options: SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  className?: string;
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  className,
}: SegmentedProps<T>) {
  return (
    <View className={cn('flex-row bg-surface-container border border-line rounded-xl p-1', className)}>
      {options.map((opt) => {
        const active = opt.id === value;
        return (
          <Pressable
            key={opt.id}
            onPress={() => onChange(opt.id)}
            className={cn(
              'flex-1 items-center justify-center px-3 py-2 rounded-lg',
              active ? 'bg-surface-elevated' : 'bg-transparent'
            )}
          >
            <Text className={cn('text-xs font-medium', active ? 'text-primary' : 'text-muted')}>
              {opt.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}