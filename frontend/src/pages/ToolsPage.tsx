import { useMemo, useState } from 'react';
import { usePolling } from '../hooks/usePolling';
import { toolsApi } from '../api/tools';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { cn } from '../lib/utils';
import { Loader2, Wrench, AlertTriangle, ChevronRight } from 'lucide-react';
import type { ToolDefinition, ToolParameterProperty } from '../types/tool';

export function ToolsPage() {
  const { data: tools, loading, error, refresh } = usePolling<ToolDefinition[]>(
    () => toolsApi.getTools(),
    30000
  );
  const [selectedName, setSelectedName] = useState<string | null>(null);

  const grouped = useMemo(() => {
    if (!tools) return [];
    const map = new Map<string, ToolDefinition[]>();
    for (const t of tools) {
      const key = t.category.toUpperCase();
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(t);
    }
    return Array.from(map.entries()).map(([category, list]) => ({ category, tools: list }));
  }, [tools]);

  const selected = useMemo(
    () => tools?.find((t) => t.name === selectedName) ?? tools?.[0] ?? null,
    [tools, selectedName]
  );

  if (loading && !tools) {
    return (
      <div className="flex items-center justify-center h-64" role="status" aria-label="Loading tools">
        <Loader2 className="w-6 h-6 text-accent-primary animate-spin" />
      </div>
    );
  }

  if (error && !tools) {
    return (
      <div className="flex items-center justify-center h-64 text-center">
        <div>
          <AlertTriangle className="w-10 h-10 text-accent-secondary mx-auto mb-3" aria-hidden="true" />
          <h2 className="text-lg font-semibold text-primary">Failed to load tool registry</h2>
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
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-primary tracking-tight">Tool Registry</h1>
          <p className="text-secondary mt-1">
            {tools ? `${tools.length} registered subroutines` : 'Loading registry'}
          </p>
        </div>
        <span className="text-xs font-mono text-muted">
          tools execute through the agent · no direct invocation endpoint
        </span>
      </div>

      {/* Master-detail */}
      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-4">
        {/* Master list */}
        <Card variant="container" className="max-h-[70vh] overflow-y-auto scrollbar-thin">
          {grouped.map(({ category, tools: list }) => (
            <div key={category}>
              <div className="sticky top-0 px-4 py-2 bg-surface-base border-b border-subtle z-10">
                <span className="text-xs font-medium uppercase tracking-wider text-accent-subtle">
                  {category}
                </span>
              </div>
              <ul role="listbox" aria-label={`${category} tools`}>
                {list.map((tool) => {
                  const isSelected = selected?.name === tool.name;
                  return (
                    <li key={tool.name}>
                      <button
                        onClick={() => setSelectedName(tool.name)}
                        className={cn(
                          'w-full text-left px-4 py-3 border-b border-subtle/50 flex items-center justify-between gap-2 transition-colors focus-ring',
                          isSelected
                            ? 'bg-surface-elevated border-l-2 border-l-accent-primary'
                            : 'hover:bg-surface-elevated/50 border-l-2 border-l-transparent'
                        )}
                        aria-selected={isSelected}
                        role="option"
                      >
                        <span className="min-w-0">
                          <span className="block font-mono text-sm text-primary truncate">
                            {tool.name}
                          </span>
                          <span className="block text-xs text-muted truncate">
                            {tool.description}
                          </span>
                        </span>
                        <ChevronRight
                          className={cn(
                            'w-4 h-4 flex-shrink-0',
                            isSelected ? 'text-accent-primary' : 'text-muted'
                          )}
                          aria-hidden="true"
                        />
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </Card>

        {/* Detail inspector */}
        {selected && (
          <Card variant="container" className="max-h-[70vh] overflow-y-auto scrollbar-thin">
            <CardHeader>
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                  <CardTitle className="font-mono text-lg">{selected.name}</CardTitle>
                  <p className="text-sm text-secondary mt-1">{selected.description}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="category" value={selected.category}>
                    {selected.category}
                  </Badge>
                  <Badge
                    variant="approval"
                    value={selected.requires_approval_by_default ? 'Requires approval' : 'Auto-permit'}
                  >
                    {selected.requires_approval_by_default ? 'Requires approval' : 'Auto-permit'}
                  </Badge>
                </div>
              </div>
            </CardHeader>

            <CardContent className="space-y-6">
              {/* Approval policy */}
              <section aria-labelledby="policy-heading">
                <h3
                  id="policy-heading"
                  className="text-xs uppercase tracking-wider text-muted mb-2"
                >
                  Approval policy
                </h3>
                <p className="text-sm text-secondary">
                  {selected.requires_approval_by_default
                    ? 'Requires user authorization when operating outside the workspace boundary. The backend security policy classifies each operation (ALLOW / REQUIRE_APPROVAL / DENY) at execution time.'
                    : 'Executed automatically when the backend security policy classifies the operation as ALLOW. Operations outside the workspace may still require approval depending on the security policy.'}
                </p>
              </section>

              {/* Parameters */}
              <section aria-labelledby="params-heading">
                <h3 id="params-heading" className="text-xs uppercase tracking-wider text-muted mb-2">
                  Parameters
                </h3>
                <ParameterTable schema={selected.parameters_schema} />
              </section>

              {/* Raw JSON schema */}
              <section aria-labelledby="schema-heading">
                <h3 id="schema-heading" className="text-xs uppercase tracking-wider text-muted mb-2">
                  JSON Schema
                </h3>
                <pre className="font-mono text-xs text-secondary bg-surface-elevated border border-subtle rounded-xl p-4 overflow-x-auto scrollbar-thin max-h-72 overflow-y-auto">
                  {JSON.stringify(selected.parameters_schema, null, 2)}
                </pre>
              </section>
            </CardContent>
          </Card>
        )}

        {!selected && (
          <Card variant="container" className="flex items-center justify-center h-48">
            <div className="text-center">
              <Wrench className="w-8 h-8 text-muted mx-auto mb-2" aria-hidden="true" />
              <p className="text-secondary text-sm">Select a tool to inspect</p>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}

function ParameterTable({ schema }: { schema: ToolDefinition['parameters_schema'] }) {
  const required = schema.required ?? [];
  const properties = Object.entries(schema.properties ?? {});

  if (properties.length === 0) {
    return <p className="text-sm text-muted">No parameters.</p>;
  }

  return (
    <div className="overflow-x-auto scrollbar-thin border border-subtle rounded-xl">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-surface-elevated text-left">
            <th className="px-3 py-2 text-xs uppercase tracking-wider text-muted font-medium">Name</th>
            <th className="px-3 py-2 text-xs uppercase tracking-wider text-muted font-medium">Type</th>
            <th className="px-3 py-2 text-xs uppercase tracking-wider text-muted font-medium">Required</th>
            <th className="px-3 py-2 text-xs uppercase tracking-wider text-muted font-medium">Default</th>
            <th className="px-3 py-2 text-xs uppercase tracking-wider text-muted font-medium">Description</th>
          </tr>
        </thead>
        <tbody>
          {properties.map(([name, prop]) => (
            <tr key={name} className="border-t border-subtle">
              <td className="px-3 py-2 font-mono text-accent-subtle whitespace-nowrap">{name}</td>
              <td className="px-3 py-2 font-mono text-secondary whitespace-nowrap">
                {prop.type}
                {prop.enum ? ` (${prop.enum.join(' | ')})` : ''}
              </td>
              <td className="px-3 py-2">
                {required.includes(name) ? (
                  <span className="text-accent-primary text-xs font-medium">required</span>
                ) : (
                  <span className="text-muted text-xs">optional</span>
                )}
              </td>
              <td className="px-3 py-2 font-mono text-secondary whitespace-nowrap">
                {prop.default !== undefined ? JSON.stringify(prop.default) : '—'}
              </td>
              <td className="px-3 py-2 text-secondary text-xs">{prop.description || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export type { ToolParameterProperty };
