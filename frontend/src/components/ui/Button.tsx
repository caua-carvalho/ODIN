import React from 'react';
import { cn } from '../../utils/cn';
import { Loader2 } from 'lucide-react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'outline' | 'amber' | 'cyan';
  size?: 'xs' | 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  className,
  variant = 'secondary',
  size = 'md',
  isLoading = false,
  disabled,
  leftIcon,
  rightIcon,
  ...props
}) => {
  const baseStyles =
    'inline-flex items-center justify-center font-medium transition-all duration-150 rounded-lg select-none focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-odin-bg active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none disabled:active:scale-100';

  const sizeStyles = {
    xs: 'text-xs px-2.5 py-1 gap-1.5',
    sm: 'text-xs px-3 py-1.5 gap-2',
    md: 'text-sm px-4 py-2 gap-2',
    lg: 'text-base px-5 py-2.5 gap-2.5',
  };

  const variantStyles = {
    primary:
      'bg-odin-primary text-black hover:bg-odin-primary-hover shadow-hud-glow font-semibold focus:ring-odin-primary',
    amber:
      'bg-odin-primary/15 text-odin-primary border border-odin-primary/40 hover:bg-odin-primary/25 hover:border-odin-primary font-medium focus:ring-odin-primary shadow-[0_0_15px_-4px_rgba(255,122,0,0.3)]',
    cyan:
      'bg-odin-cyan/15 text-odin-cyan border border-odin-cyan/40 hover:bg-odin-cyan/25 hover:border-odin-cyan font-medium focus:ring-odin-cyan shadow-[0_0_15px_-4px_rgba(0,210,255,0.3)]',
    secondary:
      'bg-odin-surface hover:bg-odin-surface-hover text-odin-text border border-odin-surface-border hover:border-odin-surface-border-strong focus:ring-zinc-600',
    outline:
      'bg-transparent hover:bg-white/5 text-odin-text border border-white/10 hover:border-white/20 focus:ring-zinc-500',
    danger:
      'bg-rose-500/15 text-rose-400 border border-rose-500/40 hover:bg-rose-500/25 hover:border-rose-500 focus:ring-rose-500 shadow-danger-glow font-semibold',
    ghost:
      'bg-transparent hover:bg-white/5 text-odin-text-muted hover:text-odin-text focus:ring-zinc-600',
  };

  return (
    <button
      className={cn(baseStyles, sizeStyles[size], variantStyles[variant], className)}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <Loader2 className="w-4 h-4 animate-spin text-current" />
      ) : (
        leftIcon && <span className="inline-flex shrink-0">{leftIcon}</span>
      )}
      <span>{children}</span>
      {!isLoading && rightIcon && <span className="inline-flex shrink-0">{rightIcon}</span>}
    </button>
  );
};
