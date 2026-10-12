import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { CommandPalette, type PaletteAction } from '../components/CommandPalette';
import { ShortcutsHelp } from '../components/ShortcutsHelp';
import { BriefingModal } from '../components/BriefingModal';
import { healthApi } from '../api/health';
import { briefingApi } from '../api/briefing';
import { WsStatusContext } from './ws-status';
import { useHotkeys, isModalOpen } from '../hooks/useHotkeys';
import { cn } from '../lib/utils';
import {
  LayoutDashboard,
  MessageSquare,
  Wrench,
  Settings,
  Shield,
  HardDrive,
  PanelLeft,
  Keyboard,
  Sparkles,
} from 'lucide-react';
import type { HealthResponse } from '../types/health';
import type { BriefingResponse } from '../types/briefing';

const PAGE_ROUTES: Record<string, string> = {
  dashboard: '/',
  chat: '/chat',
  tools: '/tools',
  skills: '/skills',
  permissions: '/permissions',
  system: '/system',
};

// 1–6 jump to a page, mirroring the sidebar order.
const PAGE_KEYS: Record<string, string> = {
  '1': 'dashboard',
  '2': 'chat',
  '3': 'tools',
  '4': 'skills',
  '5': 'permissions',
  '6': 'system',
};

const isDesktop = () => window.innerWidth >= 1024;

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(
    () => typeof window !== 'undefined' && window.innerWidth >= 1024
  );
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [activePage, setActivePage] = useState('dashboard');
  const [healthData, setHealthData] = useState<HealthResponse | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [briefingData, setBriefingData] = useState<BriefingResponse | null>(null);
  const [briefingOpen, setBriefingOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const firstNavRef = useRef<HTMLButtonElement>(null);

  const wsStatus = useMemo(
    () => ({ wsConnected, setWsConnected }),
    [wsConnected]
  );

  // Determine active page from route
  useEffect(() => {
    const path = location.pathname;
    if (path === '/chat') setActivePage('chat');
    else if (path === '/tools') setActivePage('tools');
    else if (path === '/skills') setActivePage('skills');
    else if (path === '/permissions') setActivePage('permissions');
    else if (path === '/system') setActivePage('system');
    else setActivePage('dashboard');
  }, [location.pathname]);

  // Fetch health data on mount and periodically
  const fetchHealth = useCallback(async () => {
    try {
      const data = await healthApi.getHealth();
      setHealthData(data);
    } catch (err) {
      console.error('Failed to fetch health:', err);
      setHealthData({
        status: 'offline',
        version: '0.1.0',
        model_provider: 'unknown',
        model: 'unknown',
        workspace: '',
        tools_count: 0,
        agent_ready: false,
      });
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, [fetchHealth]);

  // Load the daily briefing once on mount; show the modal only once per boot.
  useEffect(() => {
    let alive = true;
    briefingApi
      .getBriefing()
      .then((data) => {
        if (!alive) return;
        setBriefingData(data);
        if (data.should_show) setBriefingOpen(true);
      })
      .catch((err) => {
        console.error('Failed to load briefing:', err);
      });
    return () => {
      alive = false;
    };
  }, []);

  // Closing acknowledges the briefing so it doesn't reappear this boot.
  const handleCloseBriefing = useCallback(() => {
    setBriefingOpen(false);
    briefingApi.ackBriefing().catch((err) => {
      console.error('Failed to acknowledge briefing:', err);
    });
  }, []);

  // Manual reopen (command palette): refresh the payload in the background.
  const openBriefing = useCallback(() => {
    setBriefingOpen(true);
    briefingApi
      .getBriefing()
      .then(setBriefingData)
      .catch((err) => {
        console.error('Failed to load briefing:', err);
      });
  }, []);

  // Lock body scroll while the mobile drawer is open so the page behind doesn't move.
  useEffect(() => {
    if (!sidebarOpen || isDesktop()) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [sidebarOpen]);

  const activeConversationTitle = location.pathname === '/chat'
    ? new URLSearchParams(location.search).get('title') || 'New Conversation'
    : undefined;

  const closeSidebar = useCallback(() => {
    setSidebarOpen(false);
    if (!isDesktop()) menuButtonRef.current?.focus();
  }, []);

  const handleToggleSidebar = useCallback(() => {
    setSidebarOpen((prev) => {
      const next = !prev;
      if (next) {
        if (!isDesktop()) {
          // Drawer just opened — move focus to the first navigation item.
          requestAnimationFrame(() => firstNavRef.current?.focus());
        }
      } else if (!isDesktop()) {
        menuButtonRef.current?.focus();
      }
      return next;
    });
  }, []);

  const handleNavigate = useCallback(
    (page: string) => {
      setActivePage(page);
      const route = PAGE_ROUTES[page];
      // Avoid pushing duplicate history entries when already on that route.
      if (route && route !== location.pathname) navigate(route);
      // Only dismiss the drawer on mobile — keep the desktop sidebar in place.
      if (!isDesktop()) setSidebarOpen(false);
      // Move keyboard focus into the new page content for assistive tech users.
      requestAnimationFrame(() => document.getElementById('main-content')?.focus());
    },
    [navigate, location.pathname]
  );

  // Global shortcuts: command palette, help, page jumps, drawer, escape.
  useHotkeys({
    'mod+k': (e) => {
      e.preventDefault();
      setPaletteOpen(true);
    },
    'mod+b': (e) => {
      e.preventDefault();
      handleToggleSidebar();
    },
    '?': (e) => {
      e.preventDefault();
      setHelpOpen(true);
    },
    escape: () => {
      // A modal (palette/help) owns Escape while it is open.
      if (isModalOpen()) return;
      if (sidebarOpen && !isDesktop()) closeSidebar();
    },
    ...Object.fromEntries(
      Object.entries(PAGE_KEYS).map(([key, page]) => [key, () => handleNavigate(page)])
    ),
  });

  const paletteActions = useMemo<PaletteAction[]>(
    () => [
      { id: 'nav-dashboard', label: 'Go to Dashboard', hint: '1', icon: LayoutDashboard, run: () => handleNavigate('dashboard') },
      { id: 'nav-chat', label: 'Go to Chat', hint: '2', icon: MessageSquare, run: () => handleNavigate('chat') },
      { id: 'nav-tools', label: 'Go to Tools', hint: '3', icon: Wrench, run: () => handleNavigate('tools') },
      { id: 'nav-skills', label: 'Go to Skills', hint: '4', icon: Settings, run: () => handleNavigate('skills') },
      { id: 'nav-permissions', label: 'Go to Permissions', hint: '5', icon: Shield, run: () => handleNavigate('permissions') },
      { id: 'nav-system', label: 'Go to System', hint: '6', icon: HardDrive, run: () => handleNavigate('system') },
      { id: 'toggle-sidebar', label: 'Toggle navigation menu', hint: 'Ctrl B', icon: PanelLeft, run: handleToggleSidebar },
      { id: 'shortcuts-help', label: 'Show keyboard shortcuts', hint: '?', icon: Keyboard, run: () => setHelpOpen(true) },
      { id: 'show-briefing', label: 'Show daily briefing', icon: Sparkles, run: openBriefing },
    ],
    [handleNavigate, handleToggleSidebar, openBriefing]
  );

  return (
    <div className="min-h-screen bg-surface-canvas flex">
      {/* Skip link for keyboard users — jumps straight into the page content */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:px-4 focus:py-2 focus:rounded-lg focus:bg-accent-primary focus:text-white focus:text-sm focus:font-medium"
      >
        Skip to content
      </a>

      {/* Sidebar */}
      <Sidebar
        isOpen={sidebarOpen}
        activePage={activePage}
        onNavigate={handleNavigate}
        healthData={healthData || undefined}
        firstNavRef={firstNavRef}
      />

      {/* Main content area — offset for fixed sidebar on desktop */}
      <div
        className={cn(
          'flex-1 flex flex-col min-w-0',
          'motion-safe:transition-[margin] motion-safe:duration-300 motion-safe:ease-out',
          sidebarOpen && 'lg:ml-64'
        )}
      >
        {/* Top bar */}
        <TopBar
          menuButtonRef={menuButtonRef}
          isSidebarOpen={sidebarOpen}
          onMenuClick={handleToggleSidebar}
          onOpenCommands={() => setPaletteOpen(true)}
          healthData={healthData || undefined}
          wsConnected={wsConnected}
          activeConversationTitle={activeConversationTitle}
          onRefreshHealth={fetchHealth}
        />

        {/* Page content — keyed by path so routes fade in and scroll resets */}
        <main
          key={location.pathname}
          id="main-content"
          tabIndex={-1}
          className="flex-1 min-h-0 overflow-auto p-4 md:p-6 lg:p-8 animate-page-in focus:outline-none"
        >
          <WsStatusContext.Provider value={wsStatus}>
            <Outlet />
          </WsStatusContext.Provider>
        </main>
      </div>

      {/* Mobile sidebar overlay (kept in the DOM for the fade transition) */}
      <div
        className={cn(
          'fixed inset-0 z-30 bg-black/50 backdrop-blur-[2px] lg:hidden',
          'motion-safe:transition-opacity motion-safe:duration-300',
          sidebarOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
        )}
        onClick={closeSidebar}
        aria-hidden="true"
      />

      {/* Command overlays */}
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        actions={paletteActions}
      />
      <ShortcutsHelp open={helpOpen} onClose={() => setHelpOpen(false)} />
      <BriefingModal open={briefingOpen} data={briefingData} onClose={handleCloseBriefing} />
    </div>
  );
}