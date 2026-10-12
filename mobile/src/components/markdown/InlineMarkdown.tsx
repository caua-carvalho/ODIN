import type { ReactNode } from 'react';
import { Text, Linking } from 'react-native';
import type { Token, Tokens } from 'marked';

const LINK_COLOR = '#FF9A3D';

function openLink(href: string) {
  if (!href) return;
  Linking.openURL(href).catch(() => {
    /* malformed/unhandled URL — ignore */
  });
}

/** Render a single inline token. Called inside a parent <Text> so nested <Text> inherits styles. */
function renderInline(token: Token, key: number): ReactNode {
  switch (token.type) {
    case 'text': {
      const t = token as Tokens.Text;
      if (t.tokens && t.tokens.length) return t.tokens.map((child, i) => renderInline(child, i));
      return t.text;
    }
    case 'escape':
      return (token as Tokens.Escape).text;
    case 'strong': {
      const t = token as Tokens.Strong;
      return (
        <Text key={key} className="font-semibold text-primary">
          {t.tokens.map((child, i) => renderInline(child, i))}
        </Text>
      );
    }
    case 'em': {
      const t = token as Tokens.Em;
      return (
        <Text key={key} className="italic text-primary">
          {t.tokens.map((child, i) => renderInline(child, i))}
        </Text>
      );
    }
    case 'del': {
      const t = token as Tokens.Del;
      return (
        <Text key={key} className="text-muted line-through">
          {t.tokens.map((child, i) => renderInline(child, i))}
        </Text>
      );
    }
    case 'codespan':
      return (
        <Text
          key={key}
          className="rounded bg-surface-elevated px-1 font-mono text-[12px] text-primary"
        >
          {(token as Tokens.Codespan).text}
        </Text>
      );
    case 'link': {
      const t = token as Tokens.Link;
      return (
        <Text
          key={key}
          onPress={() => openLink(t.href)}
          className="underline"
          style={{ color: LINK_COLOR }}
        >
          {t.tokens && t.tokens.length
            ? t.tokens.map((child, i) => renderInline(child, i))
            : t.text}
        </Text>
      );
    }
    case 'image': {
      const t = token as Tokens.Image;
      return (
        <Text
          key={key}
          onPress={() => openLink(t.href)}
          className="underline"
          style={{ color: LINK_COLOR }}
        >
          {t.text || t.href}
        </Text>
      );
    }
    case 'br':
      return '\n';
    case 'checkbox':
      return (token as Tokens.Checkbox).checked ? '☑ ' : '☐ ';
    case 'html':
      return null; // raw HTML is stripped, matching the web console
    default: {
      const t = token as Tokens.Generic;
      if (Array.isArray(t.tokens) && t.tokens.length) {
        return t.tokens.map((child, i) => renderInline(child, i));
      }
      return t.text ?? t.raw ?? '';
    }
  }
}

/**
 * Renders the inline tokens of a markdown block. Always returns a <Text> so the
 * caller can layer a block-level className on top of the inline content.
 */
export function InlineMarkdown({ tokens, className }: { tokens?: Token[]; className?: string }) {
  if (!tokens || tokens.length === 0) return null;
  return <Text className={className}>{tokens.map((token, i) => renderInline(token, i))}</Text>;
}
