import { memo, useMemo, useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { cn } from '../../lib/utils';
import { highlightCode } from './hljs';
import { MermaidBlock } from './MermaidBlock';

interface CodeBlockProps {
  code: string;
  language?: string;
  /** While true the block is still being streamed — skip syntax highlighting. */
  streaming?: boolean;
}

/**
 * Fenced code block with a language label and copy button. Syntax highlighting
 * is applied only once the block finishes streaming so the main thread stays
 * free while chunks arrive.
 */
export const CodeBlock = memo(function CodeBlock({
  code,
  language = '',
  streaming = false,
}: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const lang = language.toLowerCase();

  const highlighted = useMemo(() => {
    if (streaming || lang === 'mermaid' || lang === '') return null;
    return highlightCode(code, lang);
  }, [code, lang, streaming]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — ignore */
    }
  };

  if (lang === 'mermaid') {
    return <MermaidBlock code={code} streaming={streaming} />;
  }

  return (
    <div className="my-3 overflow-hidden rounded-xl border border-subtle bg-surface-container">
      <div className="flex items-center justify-between border-b border-subtle bg-surface-elevated/60 px-3 py-1.5">
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted">
          {lang || 'code'}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className={cn(
            'flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-mono transition-colors focus-ring',
            copied ? 'text-green-400' : 'text-muted hover:text-primary'
          )}
          aria-label={copied ? 'Copied' : 'Copy code'}
        >
          {copied ? <Check size={13} aria-hidden="true" /> : <Copy size={13} aria-hidden="true" />}
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>
      <pre className="scrollbar-thin overflow-x-auto p-3 font-mono text-xs leading-relaxed">
        {highlighted !== null ? (
          <code className="hljs" dangerouslySetInnerHTML={{ __html: highlighted }} />
        ) : (
          <code className="text-secondary">{code}</code>
        )}
      </pre>
    </div>
  );
});
