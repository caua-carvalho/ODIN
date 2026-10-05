import { OdinService } from '../api/odinService';
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
  OdinSettings,
} from '../../types';
import {
  INITIAL_AGENT_STATUS,
  INITIAL_HARDWARE_TELEMETRY,
  INITIAL_CONVERSATIONS,
  INITIAL_MESSAGES,
  INITIAL_APPROVALS,
  INITIAL_ACTIVITIES,
  INITIAL_WORKSPACE_TREE,
  INITIAL_MEMORIES,
  INITIAL_REGISTERED_TOOLS,
  INITIAL_SKILLS,
  INITIAL_MCP_SERVERS,
  INITIAL_SETTINGS,
} from './mockData';

// In-memory state store for interactive mocking
class MockOdinServiceImpl implements OdinService {
  private agentStatus: AgentStatusSummary = { ...INITIAL_AGENT_STATUS };
  private hardwareTelemetry: HardwareTelemetry = { ...INITIAL_HARDWARE_TELEMETRY };
  private conversations: Conversation[] = [...INITIAL_CONVERSATIONS];
  private messages: Record<string, ChatMessage[]> = JSON.parse(JSON.stringify(INITIAL_MESSAGES));
  private approvals: ApprovalItem[] = [...INITIAL_APPROVALS];
  private activities: Activity[] = [...INITIAL_ACTIVITIES];
  private workspaceTree: FileNode[] = JSON.parse(JSON.stringify(INITIAL_WORKSPACE_TREE));
  private memories: MemoryItem[] = [...INITIAL_MEMORIES];
  private registeredTools: RegisteredTool[] = [...INITIAL_REGISTERED_TOOLS];
  private skills: SkillModule[] = [...INITIAL_SKILLS];
  private mcpServers: McpServer[] = [...INITIAL_MCP_SERVERS];
  private settings: OdinSettings = JSON.parse(JSON.stringify(INITIAL_SETTINGS));

  private delay(ms = 250): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async getAgentStatus(): Promise<AgentStatusSummary> {
    await this.delay(100);
    this.agentStatus.pendingApprovalsCount = this.approvals.filter((a) => a.status === 'pending').length;
    return { ...this.agentStatus };
  }

  async getHardwareTelemetry(): Promise<HardwareTelemetry> {
    await this.delay(100);
    // Simulate slight natural fluctuations in telemetry
    const jitter = (Math.random() - 0.5) * 4;
    const cpu = Math.max(8, Math.min(95, +(this.hardwareTelemetry.cpuUsage + jitter).toFixed(1)));
    const cpuHistory = [...this.hardwareTelemetry.history.cpu.slice(1), cpu];

    this.hardwareTelemetry = {
      ...this.hardwareTelemetry,
      cpuUsage: cpu,
      cpuTemp: +(42 + (cpu / 100) * 15).toFixed(1),
      diskIoRateMb: +(25 + Math.random() * 20).toFixed(1),
      uptimeSeconds: this.hardwareTelemetry.uptimeSeconds + 1,
      history: {
        ...this.hardwareTelemetry.history,
        cpu: cpuHistory,
      },
    };
    return { ...this.hardwareTelemetry };
  }

  async toggleKillSwitch(): Promise<boolean> {
    await this.delay(200);
    this.agentStatus.killSwitchActive = !this.agentStatus.killSwitchActive;
    this.agentStatus.status = this.agentStatus.killSwitchActive ? 'ERROR' : 'IDLE';
    return this.agentStatus.killSwitchActive;
  }

  async getConversations(): Promise<Conversation[]> {
    await this.delay(150);
    return [...this.conversations];
  }

  async createConversation(title = 'Nova Sessão de Diagnóstico'): Promise<Conversation> {
    await this.delay(200);
    const newConv: Conversation = {
      id: `conv-${Date.now().toString(36)}`,
      title,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      messageCount: 0,
      status: 'active',
      lastMessageSnippet: 'Sessão inicializada.',
    };
    this.conversations.unshift(newConv);
    this.messages[newConv.id] = [];
    return newConv;
  }

  async getMessages(conversationId: string): Promise<ChatMessage[]> {
    await this.delay(150);
    return this.messages[conversationId] || [];
  }

  async sendMessage(
    conversationId: string,
    content: string,
    onProgress?: (partialMessage: ChatMessage) => void
  ): Promise<ChatMessage> {
    // 1. Add user message
    const userMsg: ChatMessage = {
      id: `msg-user-${Date.now()}`,
      conversationId,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };

    if (!this.messages[conversationId]) {
      this.messages[conversationId] = [];
    }
    this.messages[conversationId].push(userMsg);

    // Update conversation metadata
    const conv = this.conversations.find((c) => c.id === conversationId);
    if (conv) {
      conv.updatedAt = new Date().toISOString();
      conv.messageCount = this.messages[conversationId].length;
      conv.lastMessageSnippet = content.slice(0, 80);
    }

    // 2. Simulate agent thinking and tool execution cycle
    this.agentStatus.status = 'THINKING';

    const assistantMsgId = `msg-odin-${Date.now()}`;
    const initialAssistantMsg: ChatMessage = {
      id: assistantMsgId,
      conversationId,
      role: 'assistant',
      content: 'Processando requisição e analisando dependências...',
      timestamp: new Date().toISOString(),
      agentState: 'THINKING',
    };

    onProgress?.(initialAssistantMsg);
    await this.delay(600);

    // 3. Simulate tool execution if applicable
    const lower = content.toLowerCase();
    let toolCalls = undefined;
    let approvalRequest = undefined;
    let finalContent = '';

    if (lower.includes('rm') || lower.includes('delet') || lower.includes('exclui') || lower.includes('remover')) {
      this.agentStatus.status = 'WAITING_APPROVAL';
      const newApprId = `appr-${Date.now().toString(36)}`;
      
      const newApproval: ApprovalItem = {
        id: newApprId,
        conversationId,
        tool: 'execute_command',
        operation: 'DELETE',
        permissionState: 'REQUIRES_APPROVAL',
        target: '/home/caua/odin-workspace/tmp/temporary_artifact.log',
        reason: 'Solicitação de remoção de artefatos de build temporários.',
        riskLevel: 'high',
        status: 'pending',
        requestedAt: new Date().toISOString(),
        commandPreview: 'rm -f /home/caua/odin-workspace/tmp/temporary_artifact.log',
      };
      
      this.approvals.unshift(newApproval);
      approvalRequest = newApproval;
      
      finalContent = `Identifiquei a necessidade de executar uma ação destrutiva no disco. De acordo com as diretrizes de governança Zero-Trust, essa operação foi interrompida e requer sua autorização explícita:`;
    } else if (lower.includes('analis') || lower.includes('teste') || lower.includes('inspect') || lower.includes('verificar')) {
      this.agentStatus.status = 'EXECUTING';
      toolCalls = [
        {
          id: `tool-${Date.now()}`,
          toolName: 'read_file',
          operation: 'READ' as const,
          args: { path: '/workspace/projects/FnCash/src/auth/jwt.service.ts' },
          status: 'success' as const,
          executionTimeMs: 86,
          output: 'Arquivo carregado com sucesso no buffer de contexto.',
        },
        {
          id: `tool-ast-${Date.now()}`,
          toolName: 'analyze_ast',
          operation: 'READ' as const,
          args: { target: 'TokenService', file: 'jwt.service.ts' },
          status: 'success' as const,
          executionTimeMs: 142,
          output: 'AST inspecionada. Todas as tipagens e retornos validados.',
        },
      ];

      // Add to activity stream
      this.activities.unshift({
        id: `act-${Date.now()}`,
        title: 'Inspeção de Símbolos AST',
        description: `Análise estática disparada a partir do comando conversacional: "${content.slice(0, 40)}..."`,
        type: 'TOOL_EXEC',
        status: 'completed',
        startedAt: new Date().toISOString(),
        completedAt: new Date(Date.now() + 228).toISOString(),
        durationMs: 228,
        result: 'Análise AST concluída com 0 violações de tipos.',
      });

      finalContent = `Executei a análise requisitada no workspace. A árvore de símbolos foi mapeada e os componentes estão consistentes com as especificações de tipagem.`;
    } else {
      this.agentStatus.status = 'EXECUTING';
      await this.delay(400);
      finalContent = `Compreendido. Registrei a solicitação no contexto de execução do Odin. Se desejar que eu realize modificações no código, execute testes ou gerencie arquivos do workspace, basta me instruir com o alvo específico.`;
    }

    this.agentStatus.status = approvalRequest ? 'WAITING_APPROVAL' : 'IDLE';

    const finalAssistantMsg: ChatMessage = {
      id: assistantMsgId,
      conversationId,
      role: 'assistant',
      content: finalContent,
      timestamp: new Date().toISOString(),
      tokenMetrics: {
        tokensUsed: Math.floor(250 + Math.random() * 400),
        tokensPerSec: Math.floor(45 + Math.random() * 20),
        latencyMs: Math.floor(180 + Math.random() * 150),
      },
      toolCalls,
      approvalRequest,
      agentState: this.agentStatus.status,
    };

    this.messages[conversationId].push(finalAssistantMsg);
    if (conv) {
      conv.messageCount = this.messages[conversationId].length;
      conv.lastMessageSnippet = finalContent.slice(0, 80);
    }

    onProgress?.(finalAssistantMsg);
    return finalAssistantMsg;
  }

  async getActivities(filter?: { status?: string; type?: string }): Promise<Activity[]> {
    await this.delay(150);
    let result = [...this.activities];
    if (filter?.status && filter.status !== 'all') {
      result = result.filter((a) => a.status === filter.status);
    }
    if (filter?.type && filter.type !== 'all') {
      result = result.filter((a) => a.type === filter.type);
    }
    return result;
  }

  async getActivityById(id: string): Promise<Activity | null> {
    await this.delay(100);
    return this.activities.find((a) => a.id === id) || null;
  }

  async getApprovals(): Promise<ApprovalItem[]> {
    await this.delay(150);
    return [...this.approvals];
  }

  async resolveApproval(approvalId: string, decision: 'allow' | 'deny'): Promise<ApprovalItem> {
    await this.delay(300);
    const item = this.approvals.find((a) => a.id === approvalId);
    if (!item) throw new Error(`Approval item not found: ${approvalId}`);

    item.status = decision === 'allow' ? 'approved' : 'rejected';
    item.permissionState = decision === 'allow' ? 'ALLOWED' : 'DENIED';
    item.resolvedAt = new Date().toISOString();
    item.resolvedBy = 'Operador (Cauã)';

    // Register activity
    this.activities.unshift({
      id: `act-resolv-${Date.now()}`,
      title: decision === 'allow' ? 'Ação Crítica Autorizada' : 'Ação Crítica Recusada',
      description: `Operação [${item.operation}] sobre "${item.target}" resolvida pelo operador.`,
      type: 'SECURITY_CHECK',
      status: decision === 'allow' ? 'completed' : 'cancelled',
      startedAt: new Date().toISOString(),
      completedAt: new Date().toISOString(),
      durationMs: 40,
      result: `Decisão: ${decision.toUpperCase()} pelo operador.`,
    });

    this.agentStatus.zeroTrustSessionValidatedCount++;
    this.agentStatus.pendingApprovalsCount = this.approvals.filter((a) => a.status === 'pending').length;
    if (this.agentStatus.pendingApprovalsCount === 0 && this.agentStatus.status === 'WAITING_APPROVAL') {
      this.agentStatus.status = 'IDLE';
    }

    return { ...item };
  }

  async getWorkspaceTree(): Promise<FileNode[]> {
    await this.delay(200);
    return JSON.parse(JSON.stringify(this.workspaceTree));
  }

  async getFileContent(filePath: string): Promise<string> {
    await this.delay(150);
    const findContent = (nodes: FileNode[]): string | null => {
      for (const node of nodes) {
        if (node.path === filePath) {
          return node.content || `// Arquivo: ${node.name}\n// Tamanho: ${node.size || 0} bytes\n`;
        }
        if (node.children) {
          const found = findContent(node.children);
          if (found !== null) return found;
        }
      }
      return null;
    };

    const content = findContent(this.workspaceTree);
    if (content !== null) return content;
    return `// Arquivo não encontrado ou sem conteúdo pré-carregado: ${filePath}`;
  }

  async searchWorkspaceFiles(query: string): Promise<FileNode[]> {
    await this.delay(150);
    if (!query.trim()) return [];
    const lower = query.toLowerCase();
    const matches: FileNode[] = [];

    const traverse = (nodes: FileNode[]) => {
      for (const node of nodes) {
        if (node.name.toLowerCase().includes(lower) || node.path.toLowerCase().includes(lower)) {
          matches.push(node);
        }
        if (node.children) {
          traverse(node.children);
        }
      }
    };

    traverse(this.workspaceTree);
    return matches;
  }

  async getMemories(category?: string, query?: string): Promise<MemoryItem[]> {
    await this.delay(150);
    let result = [...this.memories];
    if (category && category !== 'All') {
      result = result.filter((m) => m.category === category);
    }
    if (query?.trim()) {
      const q = query.toLowerCase();
      result = result.filter(
        (m) =>
          m.key.toLowerCase().includes(q) ||
          m.value.toLowerCase().includes(q) ||
          m.tags.some((t) => t.toLowerCase().includes(q))
      );
    }
    return result;
  }

  async createMemory(memory: Omit<MemoryItem, 'id' | 'createdAt' | 'updatedAt'>): Promise<MemoryItem> {
    await this.delay(200);
    const newItem: MemoryItem = {
      ...memory,
      id: `mem-${Date.now().toString(36)}`,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
    this.memories.unshift(newItem);
    return newItem;
  }

  async updateMemory(id: string, memory: Partial<MemoryItem>): Promise<MemoryItem> {
    await this.delay(200);
    const index = this.memories.findIndex((m) => m.id === id);
    if (index === -1) throw new Error(`Memory item not found: ${id}`);
    const updated = {
      ...this.memories[index],
      ...memory,
      updatedAt: new Date().toISOString(),
    };
    this.memories[index] = updated;
    return updated;
  }

  async deleteMemory(id: string): Promise<boolean> {
    await this.delay(200);
    const initialLen = this.memories.length;
    this.memories = this.memories.filter((m) => m.id !== id);
    return this.memories.length < initialLen;
  }

  async getRegisteredTools(): Promise<RegisteredTool[]> {
    await this.delay(100);
    return [...this.registeredTools];
  }

  async getSkills(): Promise<SkillModule[]> {
    await this.delay(100);
    return [...this.skills];
  }

  async getMcpServers(): Promise<McpServer[]> {
    await this.delay(100);
    return [...this.mcpServers];
  }

  async getSettings(): Promise<OdinSettings> {
    await this.delay(100);
    return JSON.parse(JSON.stringify(this.settings));
  }

  async updateSettings(newSettings: Partial<OdinSettings>): Promise<OdinSettings> {
    await this.delay(200);
    this.settings = {
      ...this.settings,
      ...newSettings,
      general: { ...this.settings.general, ...newSettings.general },
      ai: { ...this.settings.ai, ...newSettings.ai },
      security: { ...this.settings.security, ...newSettings.security },
      system: { ...this.settings.system, ...newSettings.system },
    };
    return JSON.parse(JSON.stringify(this.settings));
  }
}

export const mockOdinService = new MockOdinServiceImpl();
