import { Pressable, Text, ActivityIndicator, type PressableProps } from 'react-native';
import { cn } from '../../lib/utils';
import type { ReactNode } from 'react';

interface ButtonProps extends Omit<PressableProps, 'children'> {
  title?: string;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'subtle' | 'subtle-accent';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  disabled?: boolean;
  className?: string;
  children?: ReactNode;
}

const variants: Record<
  NonNullable<ButtonProps['variant']>,
  { container: string; text: string; spinner: string }
> = {
  primary: { container: 'bg-accent', text: 'text-canvas', spinner: '#050505' },
  secondary: { container: 'bg-surface-elevated border border-line', text: 'text-primary', spinner: '#F5F5F7' },
  ghost: { container: 'bg-transparent', text: 'text-secondary', spinner: '#A1A1A6' },
  danger: { container: 'bg-err', text: 'text-canvas', spinner: '#050505' },
  subtle: { container: 'bg-surface-container border border-line', text: 'text-primary', spinner: '#F5F5F7' },
  'subtle-accent': { container: 'bg-accent/10 border border-accent/20', text: 'text-accent', spinner: '#FF7A00' },
};

const sizes: Record<NonNullable<ButtonProps['size']>, string> = {
  sm: 'px-3 py-1.5 rounded-lg',
  md: 'px-4 py-2.5 rounded-xl',
  lg: 'px-5 py-3.5 rounded-xl',
};

export function Button({
  title,
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  className,
  children,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading;
  const v = variants[variant];
  return (
    <Pressable
      {...rest}
      disabled={isDisabled}
      className={cn(
        'flex-row items-center justify-center gap-2 active:opacity-70',
        v.container,
        sizes[size],
        isDisabled && 'opacity-40',
        className
      )}
    >
      {loading ? (
        <ActivityIndicator size="small" color={v.spinner} />
      ) : title ? (
        <Text className={cn('font-medium text-sm', v.text)}>{title}</Text>
      ) : null}
      {children}
    </Pressable>
  );
}