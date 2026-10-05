import React from 'react';
import { cn } from '../../utils/cn';

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'cyan' | 'secondary' | 'outline';
  size?: 'xs' | 'sm' | 'md';
  pulse?: boolean;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  className,
  variant = 'default',
  size = 'sm',
  pulse = false,
  ...props
}) => {
  const sizeStyles = {
    xs: 'text-[10px] px-1.5 py-0.5 leading-none',
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-1',
  };

  const variantStyles = {
    default: 'bg-zinc-800 text-zinc-300 border border-zinc-700/50',
    secondary: 'bg-zinc-900 text-zinc-400 border border-zinc-800',
    primary: 'bg-odin-primary/15 text-odin-primary border border-odin-primary/30',
    cyan: 'bg-odin-cyan/15 text-odin-cyan border border-odin-cyan/30',
    success: 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30',
    warning: 'bg-amber-500/15 text-amber-400 border border-amber-500/30',
    danger: 'bg-rose-500/15 text-rose-400 border border-rose-500/30',
    info: 'bg-blue-500/15 text-blue-400 border border-blue-500/30',
    outline: 'bg-transparent text-zinc-400 border border-zinc-700',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 font-mono font-medium rounded tracking-tight shrink-0',
        sizeStyles[size],
        variantStyles[variant],
        className
      )}
      {...props}
    >
      {pulse && (
        <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse shrink-0" />
      )}
      {children}
    </span>
  );
};
