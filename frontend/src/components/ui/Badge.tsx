import { forwardRef, type HTMLAttributes } from 'react';
import { cn, getRiskLevelColor, getStatusColor, getToolCategoryColor } from '../../lib/utils';

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'risk' | 'status' | 'category' | 'approval';
  value?: string;
}

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = 'default', value, children, ...props }, ref) => {
    let colorClass = 'bg-surface-elevated text-secondary border border-subtle';
    
    const targetValue = value || children;
    
    switch (variant) {
      case 'risk':
        colorClass = getRiskLevelColor(targetValue as string);
        break;
      case 'status':
        colorClass = getStatusColor(targetValue as string);
        break;
      case 'category':
        colorClass = getToolCategoryColor(targetValue as string);
        break;
      case 'approval':
        if (targetValue === 'Requires approval') {
          colorClass = 'text-accent-primary bg-accent-primary/10 border-accent-primary/20';
        } else if (targetValue === 'Auto-permit') {
          colorClass = 'text-green-400 bg-green-400/10 border-green-400/20';
        } else {
          colorClass = 'text-amber-400 bg-amber-400/10 border-amber-400/20';
        }
        break;
    }

    return (
      <span
        ref={ref}
        className={cn(
          'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
          colorClass,
          className
        )}
        {...props}
      >
        {children}
      </span>
    );
  }
);

Badge.displayName = 'Badge';