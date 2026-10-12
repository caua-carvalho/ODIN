/**
 * Curated highlight.js build for React Native (mirrors the web console).
 *
 * Only the languages we expect in Odin's replies are registered so the bundle
 * stays small (the full `highlight.js` pulls in hundreds of grammars). The
 * highlighted HTML is converted into styled text segments because React Native
 * cannot render HTML or CSS classes.
 */
import hljs from 'highlight.js/lib/core';

import bash from 'highlight.js/lib/languages/bash';
import c from 'highlight.js/lib/languages/c';
import cpp from 'highlight.js/lib/languages/cpp';
import csharp from 'highlight.js/lib/languages/csharp';
import css from 'highlight.js/lib/languages/css';
import diff from 'highlight.js/lib/languages/diff';
import dockerfile from 'highlight.js/lib/languages/dockerfile';
import go from 'highlight.js/lib/languages/go';
import ini from 'highlight.js/lib/languages/ini';
import java from 'highlight.js/lib/languages/java';
import javascript from 'highlight.js/lib/languages/javascript';
import json from 'highlight.js/lib/languages/json';
import markdown from 'highlight.js/lib/languages/markdown';
import php from 'highlight.js/lib/languages/php';
import python from 'highlight.js/lib/languages/python';
import ruby from 'highlight.js/lib/languages/ruby';
import rust from 'highlight.js/lib/languages/rust';
import sql from 'highlight.js/lib/languages/sql';
import typescript from 'highlight.js/lib/languages/typescript';
import xml from 'highlight.js/lib/languages/xml';
import yaml from 'highlight.js/lib/languages/yaml';

const languages = {
  bash,
  c,
  cpp,
  csharp,
  css,
  diff,
  dockerfile,
  go,
  ini,
  java,
  javascript,
  json,
  markdown,
  php,
  python,
  ruby,
  rust,
  sql,
  typescript,
  xml,
  yaml,
} as const;

for (const [name, language] of Object.entries(languages)) {
  hljs.registerLanguage(name, language);
}

hljs.registerAliases(['sh', 'shell', 'zsh', 'console'], { languageName: 'bash' });
hljs.registerAliases(['yml'], { languageName: 'yaml' });
hljs.registerAliases(['html', 'svg', 'xhtml'], { languageName: 'xml' });
hljs.registerAliases(['js', 'jsx', 'mjs', 'cjs', 'node'], { languageName: 'javascript' });
hljs.registerAliases(['ts', 'tsx'], { languageName: 'typescript' });
hljs.registerAliases(['py'], { languageName: 'python' });
hljs.registerAliases(['toml'], { languageName: 'ini' });
hljs.registerAliases(['docker'], { languageName: 'dockerfile' });
hljs.registerAliases(['patch'], { languageName: 'diff' });

/** A run of code with a resolved ODIN-palette style. */
export interface CodeSegment {
  text: string;
  color: string;
  italic?: boolean;
  bold?: boolean;
}

const DEFAULT = '#d4d4d8';
const MUTED = '#6E6E73';
const ACCENT = '#FF7A00';
const ACCENT_SUBTLE = '#00D9FF';
const GREEN = '#7ee2a8';
const PURPLE = '#c9a7ff';
const ORANGE = '#ffb86b';
const RED = '#ff7b72';

/** hljs class → palette, mirroring frontend/src/index.css `.hljs-*` rules. */
const COLOR_BY_CLASS: Record<string, string> = {
  'hljs-comment': MUTED,
  'hljs-quote': MUTED,
  'hljs-keyword': ACCENT,
  'hljs-literal': ACCENT,
  'hljs-selector-tag': ACCENT,
  'hljs-doctag': ACCENT,
  'hljs-name': ACCENT,
  'hljs-section': ACCENT,
  'hljs-string': GREEN,
  'hljs-regexp': GREEN,
  'hljs-addition': GREEN,
  'hljs-attribute': GREEN,
  'hljs-number': PURPLE,
  'hljs-symbol': PURPLE,
  'hljs-bullet': PURPLE,
  'hljs-link': PURPLE,
  'hljs-title': ACCENT_SUBTLE,
  'hljs-built_in': ACCENT_SUBTLE,
  'hljs-attr': ORANGE,
  'hljs-variable': ORANGE,
  'hljs-template-variable': ORANGE,
  'hljs-type': ORANGE,
  'hljs-selector-attr': ORANGE,
  'hljs-selector-class': ORANGE,
  'hljs-params': ORANGE,
  'hljs-deletion': RED,
};

const ENTITIES: Record<string, string> = {
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  '#x27': "'",
  '#39': "'",
  '#x2F': '/',
  '#47': '/',
};

function decodeEntities(text: string): string {
  return text.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, (match, entity: string) => {
    return ENTITIES[entity] ?? match;
  });
}

/** Resolve the nearest palette class in the span stack (innermost wins). */
function styleForStack(stack: string[]): Omit<CodeSegment, 'text'> {
  let color = DEFAULT;
  let italic = false;
  let bold = false;

  for (let i = stack.length - 1; i >= 0; i--) {
    for (const token of stack[i].split(/\s+/)) {
      if (token === 'hljs-emphasis') italic = true;
      else if (token === 'hljs-strong') bold = true;
      else if (color === DEFAULT && COLOR_BY_CLASS[token]) color = COLOR_BY_CLASS[token];
    }
  }

  return { color, italic: italic || undefined, bold: bold || undefined };
}

const TAG = /<span class="([^"]*)">|<\/span>|([^<]+)/g;

/**
 * Highlight `code` and return styled segments, or `null` when the language is
 * unknown (callers fall back to unhighlighted text).
 */
export function highlightToSegments(code: string, language: string): CodeSegment[] | null {
  const lang = language.toLowerCase();
  if (!lang || !hljs.getLanguage(lang)) return null;

  let html: string;
  try {
    html = hljs.highlight(code, { language: lang, ignoreIllegals: true }).value;
  } catch {
    return null;
  }

  const segments: CodeSegment[] = [];
  const stack: string[] = [];
  let match: RegExpExecArray | null;

  TAG.lastIndex = 0;
  while ((match = TAG.exec(html)) !== null) {
    if (match[1] !== undefined) {
      stack.push(match[1]);
    } else if (match[0] === '</span>') {
      stack.pop();
    } else if (match[2] !== undefined) {
      segments.push({ text: decodeEntities(match[2]), ...styleForStack(stack) });
    }
  }

  return segments;
}
