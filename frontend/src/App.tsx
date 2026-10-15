import { lazy } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AppLayout } from './layouts/AppLayout';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { HealthProvider } from './health/HealthContext';
import { LoginPage } from './pages/LoginPage';

// Route-level code splitting: each page (and its heavy deps, e.g. the markdown
// renderer in ChatPage) is fetched on demand instead of at boot. Suspense lives
// inside AppLayout so the shell stays mounted while a chunk loads.
const DashboardPage = lazy(() =>
  import('./pages/DashboardPage').then((m) => ({ default: m.DashboardPage }))
);
const ChatPage = lazy(() =>
  import('./pages/ChatPage').then((m) => ({ default: m.ChatPage }))
);
const ProjectsPage = lazy(() =>
  import('./pages/ProjectsPage').then((m) => ({ default: m.ProjectsPage }))
);
const ProjectDetailPage = lazy(() =>
  import('./pages/ProjectDetailPage').then((m) => ({ default: m.ProjectDetailPage }))
);
const ToolsPage = lazy(() =>
  import('./pages/ToolsPage').then((m) => ({ default: m.ToolsPage }))
);
const SkillsPage = lazy(() =>
  import('./pages/SkillsPage').then((m) => ({ default: m.SkillsPage }))
);
const PermissionsPage = lazy(() =>
  import('./pages/PermissionsPage').then((m) => ({ default: m.PermissionsPage }))
);
const SystemPage = lazy(() =>
  import('./pages/SystemPage').then((m) => ({ default: m.SystemPage }))
);

/** Shown while the auth bootstrap probes `/api/health`. */
function BootSplash() {
  return (
    <div className="min-h-screen bg-surface-canvas flex items-center justify-center">
      <span className="font-mono text-2xl font-bold text-primary tracking-tight animate-pulse">
        ODIN
      </span>
    </div>
  );
}

/**
 * Gate: the login screen replaces the whole panel until the session is valid.
 * When authentication is disabled (`disabled`) or the backend is unreachable the
 * panel renders as usual.
 */
function AuthGate() {
  const { status } = useAuth();

  if (status === 'checking') return <BootSplash />;
  if (status === 'unauthenticated') return <LoginPage />;

  return (
    <BrowserRouter>
      <HealthProvider>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/projects" element={<ProjectsPage />} />
            <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
            <Route path="/tools" element={<ToolsPage />} />
            <Route path="/skills" element={<SkillsPage />} />
            <Route path="/permissions" element={<PermissionsPage />} />
            <Route path="/system" element={<SystemPage />} />
          </Route>
        </Routes>
      </HealthProvider>
    </BrowserRouter>
  );
}

function App() {
  return (
    <AuthProvider>
      <AuthGate />
    </AuthProvider>
  );
}

export default App;
