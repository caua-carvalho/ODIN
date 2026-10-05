export type OdinAgentState = 
  | 'IDLE' 
  | 'THINKING' 
  | 'EXECUTING' 
  | 'WAITING_APPROVAL' 
  | 'COMPLETED' 
  | 'ERROR';

export type OperationType = 
  | 'READ' 
  | 'WRITE' 
  | 'EXECUTE' 
  | 'DELETE' 
  | 'EXTERNAL_ACTION';

export type PermissionState = 
  | 'ALLOWED' 
  | 'DENIED' 
  | 'REQUIRES_APPROVAL';

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'expired';

export interface ApprovalItem {
  id: string;
  conversationId: string;
  tool: string;
  operation: OperationType;
  permissionState: PermissionState;
  target: string;
  reason: string;
  riskLevel: RiskLevel;
  status: ApprovalStatus;
  requestedAt: string;
  resolvedAt?: string;
  resolvedBy?: string;
  diffPreview?: string;
  commandPreview?: string;
}

export type ActivityStatus = 
  | 'pending' 
  | 'running' 
  | 'waiting_approval' 
  | 'completed' 
  | 'failed' 
  | 'cancelled';

export type ActivityType = 
  | 'TOOL_EXEC' 
  | 'COMMAND' 
  | 'FILESYSTEM' 
  | 'THREAD_SYNC' 
  | 'SECURITY_CHECK' 
  | 'SKILL' 
  | 'DAEMON' 
  | 'MEMORY_SYNC';

export interface ActivityDetail {
  command?: string;
  path?: string;
  stdout?: string;
  stderr?: string;
  diff?: string;
  metadata?: Record<string, string | number | boolean | null>;
}

export interface Activity {
  id: string;
  title: string;
  description: string;
  type: ActivityType;
  status: ActivityStatus;
  startedAt: string;
  completedAt?: string;
  durationMs?: number;
  result?: string;
  details?: ActivityDetail;
}

export interface ToolCall {
  id: string;
  toolName: string;
  operation: OperationType;
  args: Record<string, unknown>;
  status: 'running' | 'success' | 'error' | 'pending';
  output?: string;
  executionTimeMs?: number;
  diffSnippet?: string;
}

export interface ChatMessage {
  id: string;
  conversationId: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  tokenMetrics?: {
    tokensUsed: number;
    tokensPerSec?: number;
    latencyMs?: number;
  };
  toolCalls?: ToolCall[];
  approvalRequest?: ApprovalItem;
  agentState?: OdinAgentState;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
  status: 'active' | 'archived';
  lastMessageSnippet?: string;
}

export type FileNodeType = 'file' | 'directory';

export interface FileNode {
  id: string;
  name: string;
  path: string;
  type: FileNodeType;
  size?: number;
  updatedAt: string;
  extension?: string;
  children?: FileNode[];
  modifiedByOdin?: boolean;
  lastChangeSummary?: string;
  content?: string;
}

export type MemoryCategory = 
  | 'User' 
  | 'Projects' 
  | 'Preferences' 
  | 'Knowledge' 
  | 'Tasks' 
  | 'Context';

export interface MemoryItem {
  id: string;
  key: string;
  value: string;
  category: MemoryCategory;
  confidence: number;
  tags: string[];
  createdAt: string;
  updatedAt: string;
  isPinned?: boolean;
  sourceActivityId?: string;
}

export interface HardwareTelemetry {
  cpuUsage: number;
  cpuTemp: number;
  cpuClockGhz: number;
  memoryUsedGb: number;
  memoryTotalGb: number;
  vramUsedGb: number;
  vramTotalGb: number;
  gpuName: string;
  diskUsedGb: number;
  diskTotalGb: number;
  diskIoRateMb: number;
  uptimeSeconds: number;
  heartbeatLatencyMs: number;
  history: {
    cpu: number[];
    memory: number[];
    vram: number[];
  };
}

export interface AgentStatusSummary {
  nodeId: string;
  status: OdinAgentState;
  isOnline: boolean;
  activeModel: string;
  fallbackModel: string;
  contextTokensUsed: number;
  contextTokensLimit: number;
  workerThreadsCount: number;
  activeThreadsCount: number;
  trackedGitArtifacts: number;
  rpcToolsCount: number;
  zeroTrustSessionValidatedCount: number;
  pendingApprovalsCount: number;
  killSwitchActive: boolean;
  activeWorkspacePath: string;
}

export interface RegisteredTool {
  id: string;
  name: string;
  category: string;
  description: string;
  riskLevel: RiskLevel;
  operationType: OperationType;
  enabled: boolean;
  requiresApproval: boolean;
}

export interface SkillModule {
  id: string;
  name: string;
  version: string;
  description: string;
  status: 'active' | 'standby' | 'disabled';
  triggers: string[];
}

export interface McpServer {
  id: string;
  name: string;
  transport: 'stdio' | 'sse' | 'websocket';
  endpoint: string;
  status: 'connected' | 'connecting' | 'disconnected' | 'error';
  latencyMs: number;
  toolsCount: number;
}

export interface GeneralSettings {
  assistantName: string;
  language: 'pt-BR' | 'en-US';
  theme: 'tactical' | 'obsidian' | 'auto';
  notificationsEnabled: boolean;
  soundFeedback: boolean;
  streamTokens: boolean;
  workspacePath: string;
}

export interface AiSettings {
  provider: 'gemini' | 'claude' | 'ollama' | 'openai' | 'vllm';
  primaryModel: string;
  fallbackModel: string;
  temperature: number;
  maxTokens: number;
  topP: number;
  autoFallbackEnabled: boolean;
  systemPromptAdditions: string;
}

export interface SecuritySettings {
  zeroTrustMode: boolean;
  workspaceBoundaryStrict: boolean;
  allowDestructiveCommandsWithoutConfirm: boolean;
  auditLoggingEnabled: boolean;
  autoExpireApprovalsMinutes: number;
}

export interface SystemSettings {
  version: string;
  backendUrl: string;
  websocketUrl: string;
  mockMode: boolean;
}

export interface OdinSettings {
  general: GeneralSettings;
  ai: AiSettings;
  security: SecuritySettings;
  system: SystemSettings;
}
