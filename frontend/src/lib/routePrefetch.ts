/**
 * Route chunk prefetching.
 *
 * The page components are code-split (see `App.tsx`); warming the chunk on
 * hover/focus of a sidebar item removes the loading flash when navigating on a
 * local connection. Vite/ESM dedupe the dynamic import, so the prefetched
 * module is the very one `React.lazy` later resolves.
 */
const loaders: Record<string, () => Promise<unknown>> = {
  dashboard: () => import('../pages/DashboardPage'),
  chat: () => import('../pages/ChatPage'),
  projects: () => import('../pages/ProjectsPage'),
  tools: () => import('../pages/ToolsPage'),
  skills: () => import('../pages/SkillsPage'),
  permissions: () => import('../pages/PermissionsPage'),
  system: () => import('../pages/SystemPage'),
};

export function prefetchRoute(page: string): void {
  void loaders[page]?.();
}
