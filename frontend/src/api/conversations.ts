import { api } from './client';
import type { Conversation, ConversationCreate, Message } from '../types/conversation';

export const conversationsApi = {
  listConversations: () => api.get<Conversation[]>('/api/conversations'),
  createConversation: (data: ConversationCreate) => api.post<Conversation>('/api/conversations', data),
  getConversation: (id: string) => api.get<Conversation>(`/api/conversations/${id}`),
  deleteConversation: (id: string) => api.delete<{ deleted: string }>(`/api/conversations/${id}`),
  getMessages: (conversationId: string) => api.get<Message[]>(`/api/conversations/${conversationId}/messages`),
};