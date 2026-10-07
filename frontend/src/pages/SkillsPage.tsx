import { usePolling } from '../hooks/usePolling';
import { skillsApi } from '../api/skills';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Loader2, AlertTriangle, Settings } from 'lucide-react';
import type { Skill } from '../types/skill';

export function SkillsPage() {
  const { data: skills, loading, error, refresh } = usePolling<Skill[]>(
    () => skillsApi.getSkills(),
    30000
  );

  if (loading && !skills) {
    return (
      <div className="flex items-center justify-center h-64" role="status" aria-label="Loading skills">
        <Loader2 className="w-6 h-6 text-accent-primary animate-spin" />
      </div>
    );
  }

  if (error && !skills) {
    return (
      <div className="flex items-center justify-center h-64 text-center">
        <div>
          <AlertTriangle className="w-10 h-10 text-accent-secondary mx-auto mb-3" aria-hidden="true" />
          <h2 className="text-lg font-semibold text-primary">Failed to load skills</h2>
          <p className="text-sm text-secondary mt-1 font-mono">{error}</p>
          <button
            onClick={refresh}
            className="mt-4 px-4 py-2 bg-accent-primary text-white rounded-xl text-sm hover:bg-accent-secondary transition-colors focus-ring"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-primary tracking-tight">Skills</h1>
          <p className="text-secondary mt-1">
            {skills ? `${skills.length} built-in capability modules` : 'Loading skills'}
          </p>
        </div>
        <span className="text-xs font-mono text-muted">read-only view</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {skills?.map((skill) => (
          <Card key={skill.name} variant="container">
            <CardHeader>
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3">
                  <span className="text-2xl" aria-hidden="true">
                    {skill.icon}
                  </span>
                  <CardTitle className="text-lg">{skill.name}</CardTitle>
                </div>
                <Badge
                  variant="status"
                  value={skill.enabled ? 'approved' : 'expired'}
                  className={skill.enabled ? '' : ''}
                >
                  {skill.enabled ? 'enabled' : 'disabled'}
                </Badge>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm text-secondary leading-relaxed">{skill.description}</p>

              <div>
                <p className="text-xs uppercase tracking-wider text-muted mb-2">
                  Associated tools ({skill.tools.length})
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {skill.tools.map((tool) => (
                    <span
                      key={tool}
                      className="px-2 py-1 bg-surface-elevated border border-subtle rounded-lg font-mono text-xs text-secondary"
                    >
                      {tool}
                    </span>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {skills && skills.length === 0 && (
        <Card variant="container" className="py-12 text-center">
          <Settings className="w-8 h-8 text-muted mx-auto mb-3" aria-hidden="true" />
          <p className="text-secondary">No skills registered</p>
        </Card>
      )}

      <p className="text-xs text-muted font-mono text-center">
        Skill enable/disable state is read from the backend · no mutation endpoint exists in the API
      </p>
    </div>
  );
}
