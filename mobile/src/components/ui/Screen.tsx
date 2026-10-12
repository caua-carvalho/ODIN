import { View, Text, type ViewProps } from 'react-native';
import { KeyboardAwareScrollView } from 'react-native-keyboard-controller';
import { SafeAreaView } from 'react-native-safe-area-context';
import { cn } from '../../lib/utils';
import type { ReactNode } from 'react';

interface ScreenProps extends ViewProps {
  title?: string;
  subtitle?: string;
  right?: ReactNode;
  scroll?: boolean;
  /** Bottom padding so content clears the tab bar / input. */
  padded?: boolean;
  children: ReactNode;
}

export function Screen({
  title,
  subtitle,
  right,
  scroll = true,
  padded = true,
  children,
  className,
}: ScreenProps) {
  return (
    <SafeAreaView edges={['top']} className={cn('flex-1 bg-surface-canvas', className)}>
      {title ? (
        <View className="px-4 pt-3 pb-2 flex-row items-center gap-3">
          <Text className="flex-1 text-2xl font-bold text-primary" numberOfLines={1}>
            {title}
          </Text>
          {right}
        </View>
      ) : null}
      {subtitle ? <Text className="px-4 pb-2 text-sm text-secondary">{subtitle}</Text> : null}
      {scroll ? (
        <KeyboardAwareScrollView
          className="flex-1"
          bottomOffset={16}
          contentContainerStyle={padded ? { padding: 16, paddingBottom: 96, gap: 12 } : { paddingBottom: 96, gap: 12 }}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {children}
        </KeyboardAwareScrollView>
      ) : (
        <View className="flex-1">{children}</View>
      )}
    </SafeAreaView>
  );
}