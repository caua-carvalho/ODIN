import React, { forwardRef } from 'react';
import { cn } from '../../utils/cn';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  mono?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, leftIcon, rightIcon, mono = false, ...props }, ref) => {
    return (
      <div className="w-full space-y-1.5">
        {label && (
          <label className="block text-xs font-mono text-odin-text-muted font-medium uppercase tracking-wider">
            {label}
          </label>
        )}
        <div className="relative flex items-center w-full">
          {leftIcon && (
            <div className="absolute left-3 text-odin-text-muted pointer-events-none flex items-center">
              {leftIcon}
            </div>
          )}
          <input
            ref={ref}
            className={cn(
              'w-full bg-odin-bg-subtle text-odin-text placeholder-odin-text-dim border border-odin-surface-border rounded-lg px-3.5 py-2 text-sm transition-all duration-150',
              'focus:outline-none focus:border-odin-primary/60 focus:ring-1 focus:ring-odin-primary/60',
              leftIcon && 'pl-9',
              rightIcon && 'pr-9',
              mono && 'font-mono text-xs',
              error && 'border-rose-500/60 focus:border-rose-500 focus:ring-rose-500',
              className
            )}
            {...props}
          />
          {rightIcon && (
            <div className="absolute right-3 text-odin-text-muted flex items-center">
              {rightIcon}
            </div>
          )}
        </div>
        {error && <p className="text-xs text-rose-400 font-mono mt-1">{error}</p>}
      </div>
    );
  }
);

Input.displayName = 'Input';
