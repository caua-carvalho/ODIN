import React from 'react';
import { cn } from '../../utils/cn';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'elevated' | 'amber-glow' | 'cyan-glow' | 'danger-alert' | 'ghost';
  noPadding?: boolean;
}

export const Card: React.FC<CardProps> = ({
  children,
  className,
  variant = 'default',
  noPadding = false,
  ...props
}) => {
  const variantStyles = {
    default: 'bg-odin-surface border border-odin-surface-border text-odin-text',
    elevated: 'bg-odin-bg-elevated border border-odin-surface-border-strong shadow-card-subtle text-odin-text',
    'amber-glow':
      'bg-odin-surface border border-odin-primary/40 text-odin-text amber-glow-border',
    'cyan-glow':
      'bg-odin-surface border border-odin-cyan/40 text-odin-text cyan-glow-border',
    'danger-alert':
      'bg-rose-950/20 border border-rose-500/30 text-rose-100 shadow-danger-glow',
    ghost: 'bg-transparent border border-white/5 text-odin-text',
  };

  return (
    <div
      className={cn(
        'rounded-xl transition-all duration-150',
        variantStyles[variant],
        !noPadding && 'p-4 sm:p-5',
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
};
