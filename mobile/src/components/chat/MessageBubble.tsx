import { Text, View } from 'react-native';
import { cn } from '../../lib/utils';
import { formatClock } from '../../lib/format';
import type { Message } from '../../types/conversation';

export function MessageBubble({ message }: { message: Message }) {
  if (message.role === 'tool') {
    return (
      <View className="bg-surface-container border border-line rounded-lg px-3 py-2">
        <Text className="font-mono text-xs text-muted" numberOfLines={4}>
          {message.content.slice(0, 500)}
        </Text>
      </View>
    );
  }

  if (message.role === 'system') {
    return (
      <Text className="font-mono text-xs text-muted text-center py-1">{message.content}</Text>
    );
  }

  const isUser = message.role === 'user';
  return (
    <View className={cn('pl-3 relative', isUser ? 'border-l-2 border-accent' : 'border-l-2 border-accent-subtle/40')}>
      <View className="flex-row items-center gap-2 mb-1">
        <Text
          className={cn(
            'text-[11px] font-semibold uppercase tracking-wider',
            isUser ? 'text-accent' : 'text-accent-subtle'
          )}
        >
          {isUser ? 'Operator' : 'ODIN'}
        </Text>
        <Text className="text-[10px] text-muted font-mono">{formatClock(message.created_at)}</Text>
      </View>
      <Text
        className={cn(
          'text-sm leading-relaxed whitespace-pre-wrap',
          isUser ? 'text-primary' : 'text-secondary'
        )}
      >
        {message.content || (
          <Text className="italic font-mono text-xs text-muted">streaming…</Text>
        )}
      </Text>
    </View>
  );
}