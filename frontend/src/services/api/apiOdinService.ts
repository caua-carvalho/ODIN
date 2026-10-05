import { OdinService } from './odinService';
import { mockOdinService } from '../mock/mockOdinService';
import {
  AgentStatusSummary,
  HardwareTelemetry,
  ChatMessage,
  Conversation,
  Activity,
  ApprovalItem,
  FileNode,
  MemoryItem,
  RegisteredTool,
  SkillModule,
  McpServer,
  OdinSettings
} from '../../types';

export class ApiOdinService implements OdinService {
  private baseUrl: string;

  constructor(baseUrl = 'http://127.0.0.1:8000') {
    this.baseUrl = baseUrl;
  }

  private async fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      ...options,
    });
    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }
    return response.json();
  }

  async getAgentStatus(): Promise<AgentStatusSummary> {
    try {
      const data = await this.fetchApi<{ state: AgentStatusSummary }>('/api/v1/agent/state');
      return data.state;
    } catch {
      return mockOdinService.getAgentStatus();
    }
  }

  async getHardwareTelemetry(): Promise<HardwareTelemetry> {
    try {
      return await this.fetchApi<HardwareTelemetry>('/api/v1/system/status');
    } catch {
      return mockOdinService.getHardwareTelemetry();
    }
  }

  async toggleKillSwitch(): Promise<boolean> {
    try {
      const res = await this.fetchApi<{ killSwitchActive: boolean }>('/api/v1/agent/kill-switch', {
        method: 'POST',
      });
      return res.killSwitchActive;
    } catch {
      return mockOdinService.toggleKillSwitch();
    }
  }

  async getConversations(): Promise<Conversation[]> {
    try {
      return await this.fetchApi<Conversation[]>('/api/v1/conversations');
    } catch {
      return mockOdinService.getConversations();
    }
  }

  async createConversation(title?: string): Promise<Conversation> {
    try {
      return await this.fetchApi<Conversation>('/api/v1/conversations', {
        method: 'POST',
        body: JSON.stringify({ title }),
      });
    } catch {
      return mockOdinService.createConversation(title);
    }
  }

  async getMessages(conversationId: string): Promise<ChatMessage[]> {
    try {
      return await this.fetchApi<ChatMessage[]>(`/api/v1/conversations/${conversationId}/messages`);
    } catch {
      return mockOdinService.getMessages(conversationId);
    }
  }

  async sendMessage(
    conversationId: string,
    content: string,
    onProgress?: (partialMessage: ChatMessage) => void
  ): Promise<ChatMessage> {
    try {
      const res = await this.fetchApi<ChatMessage>('/api/v1/chat', {
        method: 'POST',
        body: JSON.stringify({ conversation_id: conversationId, message: content }),
      });
      return res;
    } catch {
      return mockOdinService.sendMessage(conversationId, content, onProgress);
    }
  }

  async getActivities(filter?: { status?: string; type?: string }): Promise<Activity[]> {
    try {
      const params = new URLSearchParams();
      if (filter?.status) params.set('status', filter.status);
      if (filter?.type) params.set('type', filter.type);
      return await this.fetchApi<Activity[]>(`/api/v1/activity/timeline?${params.toString()}`);
    } catch {
      return mockOdinService.getActivities(filter);
    }
  }

  async getActivityById(id: string): Promise<Activity | null> {
    try {
      return await this.fetchApi<Activity>(`/api/v1/activity/${id}`);
    } catch {
      return mockOdinService.getActivityById(id);
    }
  }

  async getApprovals(): Promise<ApprovalItem[]> {
    try {
      const res = await this.fetchApi<{ items: ApprovalItem[] }>('/api/v1/permissions');
      return res.items;
    } catch {
      return mockOdinService.getApprovals();
    }
  }

  async resolveApproval(approvalId: string, decision: 'allow' | 'deny'): Promise<ApprovalItem> {
    try {
      return await this.fetchApi<ApprovalItem>(`/api/v1/permissions/${approvalId}/${decision}`, {
        method: 'POST',
      });
    } catch {
      return mockOdinService.resolveApproval(approvalId, decision);
    }
  }

  async getWorkspaceTree(): Promise<FileNode[]> {
    try {
      return await this.fetchApi<FileNode[]>('/api/v1/workspace/tree');
    } catch {
      return mockOdinService.getWorkspaceTree();
    }
  }

  async getFileContent(filePath: string): Promise<string> {
    try {
      const res = await this.fetchApi<{ content: string }>(`/api/v1/workspace/file?path=${encodeURIComponent(filePath)}`);
      return res.content;
    } catch {
      return mockOdinService.getFileContent(filePath);
    }
  }

  async searchWorkspaceFiles(query: string): Promise<FileNode[]> {
    try {
      return await this.fetchApi<FileNode[]>(`/api/v1/workspace/search?q=${encodeURIComponent(query)}`);
    } catch {
      return mockOdinService.searchWorkspaceFiles(query);
    }
  }

  async getMemories(category?: string, query?: string): Promise<MemoryItem[]> {
    try {
      const params = new URLSearchParams();
      if (category) params.set('category', category);
      if (query) params.set('query', query);
      return await this.fetchApi<MemoryItem[]>(`/api/v1/memory?${params.toString()}`);
    } catch {
      return mockOdinService.getMemories(category, query);
    }
  }

  async createMemory(memory: Omit<MemoryItem, 'id' | 'createdAt' | 'updatedAt'>): Promise<MemoryItem> {
    try {
      return await this.fetchApi<MemoryItem>('/api/v1/memory', {
        method: 'POST',
        body: JSON.stringify(memory),
      });
    } catch {
      return mockOdinService.createMemory(memory);
    }
  }

  async updateMemory(id: string, memory: Partial<MemoryItem>): Promise<MemoryItem> {
    try {
      return await this.fetchApi<MemoryItem>(`/api/v1/memory/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(memory),
      });
    } catch {
      return mockOdinService.updateMemory(id, memory);
    }
  }

  async deleteMemory(id: string): Promise<boolean> {
    try {
      await this.fetchApi(`/api/v1/memory/${id}`, { method: 'DELETE' });
      return true;
    } catch {
      return mockOdinService.deleteMemory(id);
    }
  }

  async getRegisteredTools(): Promise<RegisteredTool[]> {
    try {
      return await this.fetchApi<RegisteredTool[]>('/api/v1/tools');
    } catch {
      return mockOdinService.getRegisteredTools();
    }
  }

  async getSkills(): Promise<SkillModule[]> {
    try {
      return await this.fetchApi<SkillModule[]>('/api/v1/skills');
    } catch {
      return mockOdinService.getSkills();
    }
  }

  async getMcpServers(): Promise<McpServer[]> {
    try {
      return await this.fetchApi<McpServer[]>('/api/v1/mcp');
    } catch {
      return mockOdinService.getMcpServers();
    }
  }

  async getSettings(): Promise<OdinSettings> {
    try {
      return await this.fetchApi<OdinSettings>('/api/v1/settings');
    } catch {
      return mockOdinService.getSettings();
    }
  }

  async updateSettings(settings: Partial<OdinSettings>): Promise<OdinSettings> {
    try {
      return await this.fetchApi<OdinSettings>('/api/v1/settings', {
        method: 'PUT',
        body: JSON.stringify(settings),
      });
    } catch {
      return mockOdinService.updateSettings(settings);
    }
  }
}
