import { memo, useEffect, useState } from 'react';

interface MermaidBlockProps {
  code: string;
  streaming: boolean;
}

type MermaidApi = {
  initialize: (config: Record<string, unknown>) => void;
  render: (id: string, text: string) => Promise<{ svg: string }>;
};

let mermaidPromise: Promise<MermaidApi> | null = null;

/** Lazily load mermaid only when a diagram first appears, then reuse it. */
function loadMermaid(): Promise<MermaidApi> {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then((mod) => {
      const mermaid = mod.default as unknown as MermaidApi;
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'dark',
        fontFamily: '"JetBrains Mono", monospace',
      });
      return mermaid;
    });
  }
  return mermaidPromise;
}

function RawDiagramCode({ code }: { code: string }) {
  return (
    <div className="my-3 rounded-xl border border-subtle bg-surface-container overflow-hidden">
      <div className="flex items-center gap-2 border-b border-subtle bg-surface-elevated/60 px-3 py-1.5">
        <span className="text-[10px] font-mono uppercase tracking-widest text-muted">
          mermaid
        </span>
      </div>
      <pre className="scrollbar-thin overflow-x-auto p-3 font-mono text-xs leading-relaxed text-secondary">
        <code>{code}</code>
      </pre>
    </div>
  );
}

/**
 * Renders a ```mermaid fence. Diagrams only render once the block has finished
 * streaming (and are highlighted progressively), so streaming stays cheap and
 * mermaid's parser never sees a half-written definition.
 */
export const MermaidBlock = memo(function MermaidBlock({ code, streaming }: MermaidBlockProps) {
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (streaming) {
      setSvg(null);
      setError(null);
      return;
    }

    let alive = true;
    setError(null);

    loadMermaid()
      .then((mermaid) => {
        const id = `odin-mermaid-${Math.random().toString(36).slice(2)}`;
        return mermaid.render(id, code);
      })
      .then(({ svg: rendered }) => {
        if (alive) setSvg(rendered);
      })
      .catch((err: unknown) => {
        if (alive) setError(err instanceof Error ? err.message : String(err));
      });

    return () => {
      alive = false;
    };
  }, [code, streaming]);

  if (streaming) return <RawDiagramCode code={code} />;

  if (error) {
    return (
      <div className="my-3 rounded-xl border border-red-400/25 bg-red-400/[0.06] overflow-hidden">
        <div className="border-b border-red-400/20 px-3 py-1.5 text-[11px] font-medium text-red-400">
          Diagram could not be rendered
        </div>
        <pre className="scrollbar-thin overflow-x-auto p-3 font-mono text-xs leading-relaxed text-secondary">
          <code>{code}</code>
        </pre>
      </div>
    );
  }

  if (!svg) return <RawDiagramCode code={code} />;

  return (
    <div
      className="odin-mermaid my-3 flex justify-center overflow-x-auto rounded-xl border border-subtle bg-surface-container p-4"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
});
