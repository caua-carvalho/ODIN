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

export interface OdinService {
  // Agent & Telemetry
  getAgentStatus(): Promise<AgentStatusSummary>;
  getHardwareTelemetry(): Promise<HardwareTelemetry>;
  toggleKillSwitch(): Promise<boolean>;

  // Chat & Execution
  getConversations(): Promise<Conversation[]>;
  createConversation(title?: string): Promise<Conversation>;
  getMessages(conversationId: string): Promise<ChatMessage[]>;
  sendMessage(
    conversationId: string,
    content: string,
    onProgress?: (partialMessage: ChatMessage) => void
  ): Promise<ChatMessage>;

  // Activities & Execution Timeline
  getActivities(filter?: { status?: string; type?: string }): Promise<Activity[]>;
  getActivityById(id: string): Promise<Activity | null>;

  // Approvals & Security Governance
  getApprovals(): Promise<ApprovalItem[]>;
  resolveApproval(approvalId: string, decision: 'allow' | 'deny'): Promise<ApprovalItem>;

  // Workspace & File System
  getWorkspaceTree(): Promise<FileNode[]>;
  getFileContent(filePath: string): Promise<string>;
  searchWorkspaceFiles(query: string): Promise<FileNode[]>;

  // Memory & Context Management
  getMemories(category?: string, query?: string): Promise<MemoryItem[]>;
  createMemory(memory: Omit<MemoryItem, 'id' | 'createdAt' | 'updatedAt'>): Promise<MemoryItem>;
  updateMemory(id: string, memory: Partial<MemoryItem>): Promise<MemoryItem>;
  deleteMemory(id: string): Promise<boolean>;

  // Tools, Skills & MCP
  getRegisteredTools(): Promise<RegisteredTool[]>;
  getSkills(): Promise<SkillModule[]>;
  getMcpServers(): Promise<McpServer[]>;

  // Settings
  getSettings(): Promise<OdinSettings>;
  updateSettings(settings: Partial<OdinSettings>): Promise<OdinSettings>;
}
