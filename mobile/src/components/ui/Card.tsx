import { View, type ViewProps } from 'react-native';
import { cn } from '../../lib/utils';

interface CardProps extends ViewProps {
  className?: string;
}

export function Card({ className, children, ...rest }: CardProps) {
  return (
    <View
      {...rest}
      className={cn('bg-surface-base border border-line rounded-2xl p-4', className)}
    >
      {children}
    </View>
  );
}