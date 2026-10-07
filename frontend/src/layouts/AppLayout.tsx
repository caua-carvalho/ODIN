import { useState, useEffect, useCallback, useMemo } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { healthApi } from '../api/health';
import { WsStatusContext } from './ws-status';
import { cn } from '../lib/utils';
import type { HealthResponse } from '../types/health';

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const [sidebarOpen, setSidebarOpen] = useState(
    () => typeof window !== 'undefined' && window.innerWidth >= 1024
  );
  const [activePage, setActivePage] = useState('dashboard');
  const [healthData, setHealthData] = useState<HealthResponse | null>(null);
  const [wsConnected, setWsConnected] = useState(false);

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
  useEffect(() => {
    const fetchHealth = async () => {
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
    };

    fetchHealth();
    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  const activeConversationTitle = location.pathname === '/chat'
    ? new URLSearchParams(location.search).get('title') || 'New Conversation'
    : undefined;

  const handleToggleSidebar = useCallback(() => setSidebarOpen((v) => !v), []);

  const handleNavigate = (page: string) => {
    setActivePage(page);
    const routes: Record<string, string> = {
      dashboard: '/',
      chat: '/chat',
      tools: '/tools',
      skills: '/skills',
      permissions: '/permissions',
      system: '/system',
    };
    if (routes[page]) {
      navigate(routes[page]);
    }
    // Only dismiss the drawer on mobile — keep the desktop sidebar in place
    if (window.innerWidth < 1024) {
      setSidebarOpen(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface-canvas flex">
      {/* Sidebar */}
      <Sidebar
        isOpen={sidebarOpen}
        activePage={activePage}
        onNavigate={handleNavigate}
        healthData={healthData || undefined}
      />

      {/* Main content area — offset for fixed sidebar on desktop */}
      <div
        className={cn(
          'flex-1 flex flex-col min-w-0',
          sidebarOpen && 'lg:ml-64'
        )}
      >
        {/* Top bar */}
        <TopBar
          onMenuClick={handleToggleSidebar}
          healthData={healthData || undefined}
          wsConnected={wsConnected}
          activeConversationTitle={activeConversationTitle}
        />

        {/* Page content */}
        <main className="flex-1 min-h-0 overflow-auto p-4 md:p-6 lg:p-8">
          <WsStatusContext.Provider value={wsStatus}>
            <Outlet />
          </WsStatusContext.Provider>
        </main>
      </div>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}
    </div>
  );
}