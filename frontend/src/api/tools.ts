import { api } from './client';
import type { ToolDefinition } from '../types/tool';

export const toolsApi = {
  getTools: () => api.get<ToolDefinition[]>('/api/tools'),
};