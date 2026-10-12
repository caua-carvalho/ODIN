import { useState } from 'react';
import { View, Text, FlatList, Pressable, RefreshControl } from 'react-native';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'expo-router';
import { Plus, MessageSquare, Trash2, ChevronRight } from 'lucide-react-native';

import { Screen } from '../../../components/ui/Screen';
import { Button } from '../../../components/ui/Button';
import { Spinner } from '../../../components/ui/Spinner';
import { EmptyState } from '../../../components/ui/EmptyState';
import { ConfirmDialog } from '../../../components/ui/ConfirmDialog';
import { conversationsApi } from '../../../api/conversations';
import { formatRelativeTime } from '../../../lib/format';
import type { Conversation } from '../../../types/conversation';

export default function ChatListScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null);

  const conversations = useQuery({
    queryKey: ['conversations'],
    queryFn: conversationsApi.listConversations,
    refetchInterval: 20_000,
  });

  const createMutation = useMutation({
    mutationFn: () => conversationsApi.createConversation({}),
    onSuccess: (conv) => {
      void queryClient.invalidateQueries({ queryKey: ['conversations'] });
      router.push(`/chat/${conv.id}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => conversationsApi.deleteConversation(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['conversations'] }),
  });

  const confirmDelete = () => {
    if (!deleteTarget) return;
    deleteMutation.mutate(deleteTarget.id);
    setDeleteTarget(null);
  };

  return (
    <Screen
      title="Chat"
      subtitle="Conversas com o agente ODIN"
      scroll={false}
      right={
        <Button
          size="sm"
          variant="subtle-accent"
          loading={createMutation.isPending}
          accessibilityLabel="Criar conversa"
          onPress={() => createMutation.mutate()}
        >
          <Plus size={16} color="#FF7A00" />
        </Button>
      }
    >
      {conversations.isLoading ? (
        <Spinner />
      ) : conversations.isError ? (
        <EmptyState
          title="Falha ao carregar conversas"
          hint={String(conversations.error?.message ?? '')}
        />
      ) : (conversations.data ?? []).length === 0 ? (
        <EmptyState
          icon={<MessageSquare size={32} color="#6E6E73" />}
          title="Nenhuma conversa ainda"
          hint="Crie a primeira para começar a conversar com o ODIN"
        />
      ) : (
        <FlatList
          data={conversations.data}
          keyExtractor={(c) => c.id}
          className="flex-1"
          contentContainerStyle={{ paddingBottom: 96, gap: 8 }}
          refreshControl={
            <RefreshControl
              refreshing={conversations.isRefetching}
              onRefresh={() => void conversations.refetch()}
              tintColor="#FF7A00"
            />
          }
          renderItem={({ item }) => {
            const isDeleting = deleteMutation.isPending && deleteMutation.variables === item.id;
            return (
              <Pressable
                onPress={() => router.push(`/chat/${item.id}`)}
                className="bg-surface-base border border-line rounded-2xl px-4 py-3 flex-row items-center gap-3 active:bg-surface-container"
              >
                <View className="flex-1 gap-0.5">
                  <Text className="text-sm text-primary font-medium" numberOfLines={1}>
                    {item.title || 'Conversa'}
                  </Text>
                  <Text className="font-mono text-[11px] text-muted">
                    {formatRelativeTime(item.updated_at)}
                  </Text>
                </View>
                <Pressable
                  onPress={() => setDeleteTarget(item)}
                  className="p-2"
                  hitSlop={10}
                  accessibilityLabel={`Excluir conversa ${item.title || ''}`}
                >
                  {isDeleting ? (
                    <Text className="text-[10px] text-muted font-mono">…</Text>
                  ) : (
                    <Trash2 size={16} color="#6E6E73" />
                  )}
                </Pressable>
                <ChevronRight size={16} color="#3a3a40" />
              </Pressable>
            );
          }}
        />
      )}

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Excluir conversa?"
        description={
          deleteTarget
            ? `"${deleteTarget.title || 'Conversa'}" será removida permanentemente.`
            : ''
        }
        confirmLabel="Excluir"
        danger
        busy={deleteMutation.isPending}
        onConfirm={confirmDelete}
        onClose={() => setDeleteTarget(null)}
      />
    </Screen>
  );
}