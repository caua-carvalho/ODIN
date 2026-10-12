import { memo, useDeferredValue, useMemo } from 'react';
import { Text, View } from 'react-native';
import { marked, type Token, type Tokens } from 'marked';
import { cn } from '../../lib/utils';
import { Callout } from './Callout';
import { CodeBlock } from './CodeBlock';
import { InlineMarkdown } from './InlineMarkdown';
import { parseCallout, splitMarkdownBlocks } from './blocks';

const HEADING_CLASS: Record<number, string> = {
  1: 'text-lg',
  2: 'text-base',
  3: 'text-[15px]',
  4: 'text-sm',
  5: 'text-sm',
  6: 'text-sm',
};

function lexer(content: string): Token[] {
  return marked.lexer(content) as Token[];
}

function alignClass(align: Tokens.Table['align'][number]): string {
  if (align === 'center') return 'text-center';
  if (align === 'right') return 'text-right';
  return 'text-left';
}

function Table({ token }: { token: Tokens.Table }) {
  return (
    <View className="my-3 overflow-hidden rounded-xl border border-line">
      <View className="flex-row bg-surface-elevated">
        {token.header.map((cell, i) => (
          <Text
            key={i}
            className={cn('flex-1 px-3 py-2 text-[12px] font-semibold text-primary', alignClass(cell.align))}
          >
            <InlineMarkdown tokens={cell.tokens} />
          </Text>
        ))}
      </View>
      {token.rows.map((row, ri) => (
        <View key={ri} className="flex-row border-t border-line">
          {row.map((cell, ci) => (
            <Text
              key={ci}
              className={cn('flex-1 px-3 py-1.5 text-[12px] leading-relaxed text-secondary', alignClass(cell.align))}
            >
              <InlineMarkdown tokens={cell.tokens} />
            </Text>
          ))}
        </View>
      ))}
    </View>
  );
}

function ListView({ token, streaming }: { token: Tokens.List; streaming: boolean }) {
  const start = typeof token.start === 'number' ? token.start : 1;
  return (
    <View className="my-1">
      {token.items.map((item, i) => (
        <View key={i} className="flex-row items-start gap-2">
          <Text className="text-sm leading-relaxed text-muted">
            {item.task
              ? item.checked
                ? '☑'
                : '☐'
              : token.ordered
                ? `${start + i}.`
                : '•'}
          </Text>
          <View className="flex-1">
            <BlockTokens tokens={item.tokens} streaming={streaming} />
          </View>
        </View>
      ))}
    </View>
  );
}

function BlockToken({ token, streaming }: { token: Token; streaming: boolean }) {
  switch (token.type) {
    case 'space':
      return null;
    case 'hr':
      return <View className="my-3 h-px bg-line" />;
    case 'heading': {
      const t = token as Tokens.Heading;
      return (
        <Text
          className={cn('mb-1 mt-3 font-semibold text-primary', HEADING_CLASS[t.depth] ?? 'text-sm')}
        >
          <InlineMarkdown tokens={t.tokens} />
        </Text>
      );
    }
    case 'paragraph': {
      const t = token as Tokens.Paragraph;
      return (
        <Text className="my-1 text-sm leading-relaxed text-secondary">
          <InlineMarkdown tokens={t.tokens} />
        </Text>
      );
    }
    case 'code': {
      const t = token as Tokens.Code;
      return <CodeBlock code={t.text} language={t.lang ?? ''} streaming={streaming} />;
    }
    case 'blockquote': {
      const t = token as Tokens.Blockquote;
      return (
        <View className="my-2 border-l-2 border-line pl-3">
          <BlockTokens tokens={t.tokens} streaming={streaming} />
        </View>
      );
    }
    case 'list':
      return <ListView token={token as Tokens.List} streaming={streaming} />;
    case 'table':
      return <Table token={token as Tokens.Table} />;
    case 'html':
      return null; // raw HTML is stripped, matching the web console
    default: {
      const t = token as Tokens.Generic;
      if (Array.isArray(t.tokens) && t.tokens.length) {
        return (
          <Text className="my-1 text-sm leading-relaxed text-secondary">
            <InlineMarkdown tokens={t.tokens} />
          </Text>
        );
      }
      return t.raw ? <Text className="my-1 font-mono text-xs text-muted">{t.raw}</Text> : null;
    }
  }
}

function BlockTokens({ tokens, streaming }: { tokens: Token[]; streaming: boolean }) {
  return (
    <>
      {tokens.map((token, i) => (
        <BlockToken key={i} token={token} streaming={streaming} />
      ))}
    </>
  );
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
  const tokens = useMemo(() => lexer(content), [content]);
  return <BlockTokens tokens={tokens} streaming={streaming} />;
});

export interface MarkdownRendererProps {
  content: string;
  /** True while the message is still being streamed. */
  streaming?: boolean;
}

/**
 * Renders assistant messages as GitHub-flavored Markdown (tables, lists, links,
 * inline code, fenced code, callouts and mermaid-as-source), mirroring the web
 * console's display contract. Content is split into blocks so closed blocks
 * memoize while only the live tail re-parses as chunks arrive.
 */
export const MarkdownRenderer = memo(function MarkdownRenderer({
  content,
  streaming = false,
}: MarkdownRendererProps) {
  // Defer parsing so scrolling stays responsive while chunks arrive.
  const deferred = useDeferredValue(content);
  const blocks = useMemo(() => splitMarkdownBlocks(deferred), [deferred]);

  return (
    <View>
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

        return <MarkdownBlock key={index} content={block.content} streaming={blockStreaming} />;
      })}
    </View>
  );
});
