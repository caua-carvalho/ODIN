import { useRef, useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  ScrollView,
  TextInput,
  KeyboardAvoidingView,
  Platform,
  Pressable,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ArrowLeft, RefreshCw, SendHorizonal, Loader2, AlertTriangle } from 'lucide-react-native';

import { useOdinSession } from '../../../hooks/useOdinSession';
import { conversationsApi } from '../../../api/conversations';
import { MessageBubble } from '../../../components/chat/MessageBubble';
import { ToolCallCard } from '../../../components/chat/ToolCallCard';
import { PermissionInline } from '../../../components/chat/PermissionInline';
import { StatusBadge } from '../../../components/ui/Badges';
import { Button } from '../../../components/ui/Button';

const SESSION_LABELS: Record<string, string> = {
  idle: 'parado',
  thinking: 'pensando',
  waiting_auth: 'aguardando aprovação',
  streaming: 'respondendo',
  error: 'erro',
};

export default function ConversationScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const conversationId = typeof id === 'string' ? id : null;

  // Real conversation title (falls back to a generic label while loading).
  const conversation = useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () => conversationsApi.getConversation(conversationId as string),
    enabled: !!conversationId,
    staleTime: 30_000,
  });

  const [input, setInput] = useState('');
  const scrollRef = useRef<ScrollView>(null);
  const stickToBottomRef = useRef(true);

  const session = useOdinSession(conversationId);

  const handleSend = useCallback(() => {
    if (!input.trim() || session.sessionState !== 'idle') return;
    session.sendMessage(input);
    setInput('');
  }, [input, session]);

  const handleScroll = useCallback((y: number, contentHeight: number, layoutHeight: number) => {
    stickToBottomRef.current = contentHeight - y - layoutHeight < 120;
  }, []);

  useEffect(() => {
    const { timeline, statusMessage } = session;
    if (stickToBottomRef.current && (timeline.length > 0 || statusMessage)) {
      requestAnimationFrame(() => {
        scrollRef.current?.scrollToEnd({ animated: true });
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.timeline, session.statusMessage, session.sessionState]);

  const busy = session.sessionState !== 'idle';

  return (
    <SafeAreaView edges={['top']} className="flex-1 bg-surface-canvas">
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        className="flex-1"
        keyboardVerticalOffset={0}
      >
        {/* Header */}
        <View className="px-4 py-2.5 flex-row items-center gap-3 border-b border-line bg-surface-base">
          <Pressable onPress={() => router.back()} hitSlop={10} className="p-1" accessibilityLabel="Voltar">
            <ArrowLeft size={20} color="#A1A1A6" />
          </Pressable>
          <View className="flex-1 min-w-0">
            <Text className="text-sm font-medium text-primary" numberOfLines={1}>
              {conversation.data?.title || 'Nova conversa'}
            </Text>
            <View className="flex-row items-center gap-2 mt-0.5">
              <StatusBadge status={session.wsConnected ? 'ok' : 'err'} label={session.wsConnected ? 'WS' : 'offline'} />
              {busy ? (
                <StatusBadge status="warn" label={SESSION_LABELS[session.sessionState] ?? session.sessionState} />
              ) : null}
            </View>
          </View>
          <Button size="sm" variant="ghost" accessibilityLabel="Recarregar mensagens" onPress={() => session.reloadHistory()}>
            <RefreshCw size={16} color="#6E6E73" />
          </Button>
        </View>

        {/* Timeline */}
        <ScrollView
          ref={scrollRef}
          className="flex-1"
          contentContainerStyle={{ padding: 16, gap: 14, paddingBottom: 24 }}
          onScroll={(e) => {
            const { contentOffset, contentSize, layoutMeasurement } = e.nativeEvent;
            handleScroll(contentOffset.y, contentSize.height, layoutMeasurement.height);
          }}
          scrollEventThrottle={64}
          keyboardShouldPersistTaps="handled"
        >
          {session.isLoadingHistory ? (
            <View className="items-center py-12">
              <Loader2 size={22} color="#FF7A00" />
            </View>
          ) : null}

          {session.historyError ? (
            <View className="rounded-xl border border-err/20 bg-err/5 p-3 gap-2">
              <View className="flex-row items-start gap-2">
                <AlertTriangle size={16} color="#f87171" />
                <Text className="flex-1 text-xs text-err font-medium">
                  Falha ao carregar mensagens
                </Text>
              </View>
              <Text className="font-mono text-[11px] text-err/80">{session.historyError}</Text>
              <Button size="sm" variant="ghost" title="Tentar novamente" onPress={() => session.reloadHistory()} />
            </View>
          ) : null}

          {conversationId && !session.isLoadingHistory && session.timeline.length === 0 && !session.historyError ? (
            <View className="items-center py-16 gap-1">
              <Text className="text-sm text-secondary">Sessão vazia</Text>
              <Text className="text-xs text-muted">Envie uma mensagem para começar a trabalhar com o ODIN</Text>
            </View>
          ) : null}

          {session.timeline.map((entry) => {
            if (entry.kind === 'message') {
              return <MessageBubble key={entry.id} message={entry.message} />;
            }
            if (entry.kind === 'tool') {
              return <ToolCallCard key={entry.id} execution={entry.execution} />;
            }
            return <PermissionInline key={entry.id} event={entry.event} resolved={entry.resolved} />;
          })}

          {busy && session.statusMessage ? (
            <View className="flex-row items-center gap-2 py-1">
              <Loader2 size={14} color="#FF7A00" />
              <Text className="font-mono text-xs text-secondary">{session.statusMessage}</Text>
            </View>
          ) : null}

          {session.streamError ? (
            <View className="rounded-xl border border-err/20 bg-err/5 p-3">
              <Text className="text-xs text-err font-medium mb-1">Erro do agente</Text>
              <Text className="font-mono text-[11px] text-err/80">{session.streamError}</Text>
            </View>
          ) : null}
        </ScrollView>

        {/* Input */}
        <View className="border-t border-line bg-surface-base px-3 py-2.5">
          <View className="flex-row items-end gap-2 bg-surface-elevated border border-line rounded-xl px-3 py-2">
            <Text className="text-accent font-mono text-sm pb-1">›</Text>
            <TextInput
              className="flex-1 text-sm text-primary font-mono min-h-[36px] max-h-[120px] py-0"
              placeholder={
                busy
                  ? 'ODIN trabalhando…'
                  : !session.wsConnected
                    ? 'Reconectando…'
                    : 'Mensagem para o ODIN…'
              }
              placeholderTextColor="#6E6E73"
              multiline
              value={input}
              onChangeText={setInput}
              onSubmitEditing={handleSend}
              editable={!busy}
              returnKeyType="send"
            />
            <Button
              size="sm"
              variant="primary"
              accessibilityLabel="Enviar mensagem"
              disabled={!input.trim() || busy || !session.wsConnected}
              onPress={handleSend}
            >
              <SendHorizonal size={16} color="#050505" />
            </Button>
          </View>
          {!session.wsConnected && conversationId ? (
            <Text className="text-[11px] text-err mt-1 font-mono">
              WebSocket desconectado — aguardando reconexão automática
            </Text>
          ) : null}
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}