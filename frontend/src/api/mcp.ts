import { api } from './client';
import type { MCPServer } from '../types/mcp';

export const mcpApi = {
  getMCPServers: () => api.get<MCPServer[]>('/api/mcp'),
};