import type { ReactNode } from 'react';
import { Text, Linking, Platform } from 'react-native';
import type { Token, Tokens } from 'marked';

const LINK_COLOR = '#FF9A3D';

/**
 * React Native only accepts a single font name (not a CSS font stack), so the
 * `font-mono` utility (which resolves to a comma-separated stack) silently
 * falls back to the system font here. Pick a real monospace face per platform.
 */
const MONO_FONT = Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' });

/**
 * Inline code chip. Styles are applied inline (not via `className`) because this
 * is a <Text> nested inside another <Text>: nested-text class resolution is
 * unreliable, and when the background applies but the colour does not (or vice
 * versa) the chip renders as a solid block with invisible text.
 */
const INLINE_CODE_STYLE = {
  backgroundColor: '#171719', // --color-surface-elevated
  color: '#F5F5F7', // --color-text-primary
  borderWidth: 1,
  borderColor: 'rgba(255, 255, 255, 0.10)', // --color-border-subtle
  borderRadius: 5,
  paddingHorizontal: 5,
  fontSize: 12.5,
  fontFamily: MONO_FONT,
} as const;

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
        <Text key={key} style={INLINE_CODE_STYLE}>
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
