/**
 * Markdown helpers for streaming chat.
 *
 * `splitMarkdownBlocks` breaks raw markdown into top-level blocks so that
 * completed blocks can be memoized and only the streaming tail re-parses on
 * every chunk. The splitter is deliberately conservative: it never tears a
 * list, table or blockquote apart, even if that means a slightly coarser split.
 */

export interface MarkdownBlock {
  content: string;
  /** True when this is the final block and its code fence is still open. */
  open: boolean;
}

export interface CalloutData {
  type: string;
  body: string;
}

const LIST_ITEM = /^\s*(?:[-*+]|\d+\.)\s+/;
const BLOCKQUOTE = /^\s*>/;
const TABLE_ROW = /^\s*\|/;
const INDENTED = /^\s{2,}\S/;
const FENCE = /^\s*(`{3,}|~{3,})(.*)$/;

const isBlank = (line: string): boolean => line.trim() === '';

/**
 * Whether a blank line between `lastLine` and `nextLine` is a *safe* split
 * point. If merging is required to preserve the construct, return true.
 */
function shouldMerge(lastLine: string, nextLine: string): boolean {
  // Indented content continues the construct above (list item body, etc.).
  if (INDENTED.test(nextLine)) return true;
  if (LIST_ITEM.test(lastLine) && LIST_ITEM.test(nextLine)) return true;
  if (BLOCKQUOTE.test(lastLine) && BLOCKQUOTE.test(nextLine)) return true;
  if (TABLE_ROW.test(lastLine) && TABLE_ROW.test(nextLine)) return true;
  return false;
}

function isFenceClose(line: string, fence: string): boolean {
  const match = line.match(FENCE);
  if (!match) return false;
  return (
    match[1][0] === fence[0] &&
    match[1].length >= fence.length &&
    match[2].trim() === ''
  );
}

export function splitMarkdownBlocks(source: string): MarkdownBlock[] {
  const lines = source.split('\n');
  const blocks: string[] = [];
  let current: string[] = [];
  let fence: string | null = null;

  const flush = () => {
    const content = current.join('\n').replace(/^\n+|\n+$/g, '');
    if (content) blocks.push(content);
    current = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (fence) {
      current.push(line);
      if (isFenceClose(line, fence)) fence = null;
      continue;
    }

    const openMatch = line.match(FENCE);
    if (openMatch) {
      current.push(line);
      fence = openMatch[1];
      continue;
    }

    if (isBlank(line)) {
      if (current.length === 0) continue;
      let j = i + 1;
      while (j < lines.length && isBlank(lines[j])) j++;
      const next = lines[j] ?? '';
      const lastNonBlank =
        [...current].reverse().find((l) => !isBlank(l)) ?? '';
      if (next !== '' && shouldMerge(lastNonBlank, next)) {
        current.push(line); // keep the construct together
      } else {
        flush();
      }
      continue;
    }

    current.push(line);
  }

  flush();

  return blocks.map((content, index) => ({
    content,
    open: fence !== null && index === blocks.length - 1,
  }));
}

/**
 * Detect a GitHub-style alert blockquote (`> [!NOTE] …`) and return its type
 * plus the inner markdown (with the `>` markers stripped). The block is
 * rendered by a dedicated `<Callout>` component.
 */
export function parseCallout(content: string): CalloutData | null {
  const lines = content.split('\n');
  const match = lines[0].match(/^\s*>\s*\[!(\w+)\]\s?(.*)$/);
  if (!match) return null;

  const bodyLines = [match[2]];
  for (let i = 1; i < lines.length; i++) {
    bodyLines.push(lines[i].replace(/^\s*>\s?/, ''));
  }

  return { type: match[1].toLowerCase(), body: bodyLines.join('\n').trim() };
}
