import { memo, useMemo, useState } from 'react';
import { Pressable, ScrollView, Text, View, Platform } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Check, Copy } from 'lucide-react-native';
import { cn } from '../../lib/utils';
import { highlightToSegments } from './hljs';

/** React Native needs a real font name, not the CSS `font-mono` stack. */
const MONO_FONT = Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' });

interface CodeBlockProps {
  code: string;
  language?: string;
  /** While true the block is still being streamed — skip syntax highlighting. */
  streaming?: boolean;
}

/**
 * Fenced code block with a language label and copy button. Syntax highlighting
 * is applied only once the block finishes streaming so the main thread stays
 * free while chunks arrive. `mermaid` fences fall back to their source (React
 * Native has no DOM to render the diagram into).
 */
export const CodeBlock = memo(function CodeBlock({
  code,
  language = '',
  streaming = false,
}: CodeBlockProps) {
  const [copied, setCopied] = useState(false);
  const lang = language.toLowerCase();

  const segments = useMemo(() => {
    if (streaming || lang === 'mermaid' || lang === '') return null;
    return highlightToSegments(code, lang);
  }, [code, lang, streaming]);

  const handleCopy = async () => {
    try {
      await Clipboard.setStringAsync(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — ignore */
    }
  };

  return (
    <View className="my-3 overflow-hidden rounded-xl border border-line bg-surface-container">
      <View className="flex-row items-center justify-between border-b border-line bg-surface-elevated/60 px-3 py-1.5">
        <Text className="font-mono text-[10px] uppercase tracking-widest text-muted">
          {lang || 'code'}
        </Text>
        <Pressable
          onPress={handleCopy}
          hitSlop={8}
          accessibilityLabel={copied ? 'Copiado' : 'Copiar código'}
          className="flex-row items-center gap-1 rounded-md px-1.5 py-0.5 active:opacity-70"
        >
          {copied ? <Check size={13} color="#34d399" /> : <Copy size={13} color="#6E6E73" />}
          <Text className={cn('font-mono text-[11px]', copied ? 'text-ok' : 'text-muted')}>
            {copied ? 'Copiado' : 'Copiar'}
          </Text>
        </Pressable>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        <Text
          selectable
          className="p-3 text-xs leading-relaxed"
          style={{ color: '#d4d4d8', fontFamily: MONO_FONT }}
        >
          {segments
            ? segments.map((segment, index) => (
                <Text
                  key={index}
                  style={{
                    color: segment.color,
                    fontStyle: segment.italic ? 'italic' : 'normal',
                    fontWeight: segment.bold ? '600' : 'normal',
                  }}
                >
                  {segment.text}
                </Text>
              ))
            : code}
        </Text>
      </ScrollView>
    </View>
  );
});
