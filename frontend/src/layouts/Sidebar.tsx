import { cn } from '../lib/utils';
import { Button } from '../components/ui/Button';
import { Separator } from '../components/ui/Separator';
import {
  LayoutDashboard,
  MessageSquare,
  Wrench,
  Settings,
  Shield,
  HardDrive,
} from 'lucide-react';
import type { HealthResponse } from '../types/health';

interface SidebarProps {
  isOpen: boolean;
  activePage: string;
  onNavigate: (page: string) => void;
  healthData?: HealthResponse;
}

const navigation = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'chat', label: 'Chat', icon: MessageSquare },
  { id: 'tools', label: 'Tools', icon: Wrench },
  { id: 'skills', label: 'Skills', icon: Settings },
  { id: 'permissions', label: 'Permissions', icon: Shield },
  { id: 'system', label: 'System', icon: HardDrive },
];

export function Sidebar({ isOpen, activePage, onNavigate, healthData }: SidebarProps) {
  if (!isOpen) return null;

  const isReady = healthData?.status === 'online' && healthData.agent_ready;

  return (
    <aside
      className="fixed left-0 top-0 z-40 h-full w-64 bg-surface-base border-r border-subtle flex flex-col"
      aria-label="Main navigation"
    >
      {/* Brand header */}
      <div className="flex items-center h-16 px-5 border-b border-subtle">
        <span className="font-mono text-xl font-bold text-primary tracking-tight select-none">
          ODIN
        </span>
        <span className="ml-auto text-[10px] font-mono text-muted uppercase tracking-widest">
          v{healthData?.version ?? '—'}
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto scrollbar-thin" aria-label="Primary navigation">
        {navigation.map((item) => {
          const Icon = item.icon;
          const isActive = activePage === item.id;

          return (
            <Button
              key={item.id}
              variant={isActive ? 'primary' : 'ghost'}
              size="md"
              className="w-full justify-start gap-3 px-3 rounded-xl"
              onClick={() => onNavigate(item.id)}
              aria-current={isActive ? 'page' : undefined}
            >
              <Icon size={18} aria-hidden="true" />
              <span className="font-medium">{item.label}</span>
            </Button>
          );
        })}
      </nav>

      <Separator className="mx-3" />

      {/* Runtime info */}
      <div className="px-4 py-4 space-y-3">
        {healthData && (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  'w-2 h-2 rounded-full',
                  isReady ? 'bg-green-400' : 'bg-red-400'
                )}
                aria-hidden="true"
              />
              <span className="text-xs font-medium text-primary">
                {isReady ? 'ONLINE' : 'OFFLINE'}
              </span>
            </div>
            <div className="flex items-center gap-1.5 text-xs text-secondary font-mono min-w-0">
              <span className="truncate">{healthData.model_provider}</span>
              <span className="text-muted">/</span>
              <span className="truncate">{healthData.model}</span>
            </div>
            <div className="text-xs text-secondary font-mono">
              {healthData.tools_count} tools
            </div>
          </div>
        )}

        <Separator />

        <div className="flex items-center justify-between text-xs font-mono">
          <span className="text-secondary">LOCAL_01</span>
          <span className="text-muted">{healthData ? `v${healthData.version}` : 'v—'}</span>
        </div>
      </div>
    </aside>
  );
}
