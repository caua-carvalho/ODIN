import { isValidElement, memo, useDeferredValue, useMemo, type ReactNode } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Callout } from './Callout';
import { CodeBlock } from './CodeBlock';
import { parseCallout, splitMarkdownBlocks } from './blocks';

const REMARK_PLUGINS = [remarkGfm];

function extractText(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === 'boolean') return '';
  if (typeof node === 'string') return node;
  if (typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(extractText).join('');
  if (isValidElement(node)) {
    return extractText((node.props as { children?: ReactNode }).children);
  }
  return '';
}

function buildComponents(streaming: boolean): Components {
  return {
    // External links open in a new tab; raw HTML stays disabled (no rehype-raw).
    a: ({ href, title, children }) => (
      <a href={href} title={title} target="_blank" rel="noreferrer noopener">
        {children}
      </a>
    ),
    // Fenced code blocks arrive as <pre><code class="language-x">…</code></pre>.
    pre: ({ children }) => {
      const child = Array.isArray(children) ? children[0] : children;
      if (isValidElement(child)) {
        const props = child.props as { className?: string; children?: ReactNode };
        const lang = /language-([\w-]+)/.exec(props.className ?? '')?.[1] ?? '';
        const code = extractText(props.children).replace(/\n$/, '');
        return <CodeBlock code={code} language={lang} streaming={streaming} />;
      }
      return <pre>{children}</pre>;
    },
    code: ({ className, children }) =>
      /language-/.test(className ?? '') ? (
        <code className={className}>{children}</code>
      ) : (
        <code className="odin-inline-code">{children}</code>
      ),
    table: ({ children }) => (
      <div className="odin-table-wrap scrollbar-thin">
        <table>{children}</table>
      </div>
    ),
    blockquote: ({ children }) => (
      <blockquote className="odin-blockquote">{children}</blockquote>
    ),
  };
}

/**
 * A single top-level markdown block. Memoized on `content` (a string) so that,
 * during streaming, already-closed blocks are never re-parsed or re-rendered —
 * only the live tail block updates on each chunk.
 */
const MarkdownBlock = memo(function MarkdownBlock({
  content,
  streaming,
}: {
  content: string;
  streaming: boolean;
}) {
  const components = useMemo(() => buildComponents(streaming), [streaming]);
  return (
    <ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={components}>
      {content}
    </ReactMarkdown>
  );
});

export interface MarkdownRendererProps {
  content: string;
  /** True while the message is still being streamed. */
  streaming?: boolean;
}

export const MarkdownRenderer = memo(function MarkdownRenderer({
  content,
  streaming = false,
}: MarkdownRendererProps) {
  // Defer markdown parsing so typing/scroll stay responsive while chunks arrive.
  const deferred = useDeferredValue(content);
  const blocks = useMemo(() => splitMarkdownBlocks(deferred), [deferred]);

  return (
    <div className="odin-markdown">
      {blocks.map((block, index) => {
        const isTail = index === blocks.length - 1;
        const blockStreaming = isTail && streaming && block.open;
        const callout = parseCallout(block.content);

        if (callout) {
          return (
            <Callout key={index} type={callout.type}>
              <MarkdownBlock content={callout.body} streaming={blockStreaming} />
            </Callout>
          );
        }

        return (
          <MarkdownBlock key={index} content={block.content} streaming={blockStreaming} />
        );
      })}
    </div>
  );
});
