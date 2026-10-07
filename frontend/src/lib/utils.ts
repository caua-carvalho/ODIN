import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  
  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return formatDate(dateString);
}

export function getRiskLevelColor(risk: string): string {
  switch (risk) {
    case 'critical': return 'text-accent-secondary bg-accent-secondary/10 border-accent-secondary/20';
    case 'high': return 'text-accent-secondary bg-accent-secondary/10 border-accent-secondary/20';
    case 'medium': return 'text-amber-400 bg-amber-400/10 border-amber-400/20';
    case 'low': return 'text-accent-subtle bg-accent-subtle/10 border-accent-subtle/20';
    default: return 'text-muted bg-surface-elevated border-subtle';
  }
}

export function getStatusColor(status: string): string {
  switch (status) {
    case 'approved': return 'text-green-400 bg-green-400/10 border-green-400/20';
    case 'denied': return 'text-red-400 bg-red-400/10 border-red-400/20';
    case 'pending': return 'text-accent-primary bg-accent-primary/10 border-accent-primary/20';
    case 'expired': return 'text-muted bg-surface-elevated border-subtle';
    default: return 'text-muted bg-surface-elevated border-subtle';
  }
}

export function getToolCategoryColor(category: string): string {
  switch (category) {
    case 'filesystem': return 'text-blue-400';
    case 'shell': return 'text-purple-400';
    default: return 'text-muted';
  }
}