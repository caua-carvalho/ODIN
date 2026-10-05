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

export const INITIAL_AGENT_STATUS: AgentStatusSummary = {
  nodeId: 'ODIN_NODE_01',
  status: 'IDLE',
  isOnline: true,
  activeModel: 'Gemini 2.5 Flash / Claude 3.7 Sonnet',
  fallbackModel: 'Ollama (qwen2.5-coder:14b-local)',
  contextTokensUsed: 14280,
  contextTokensLimit: 200000,
  workerThreadsCount: 8,
  activeThreadsCount: 1,
  trackedGitArtifacts: 42,
  rpcToolsCount: 14,
  zeroTrustSessionValidatedCount: 18,
  pendingApprovalsCount: 2,
  killSwitchActive: false,
  activeWorkspacePath: '/home/caua/odin-workspace',
};

export const INITIAL_HARDWARE_TELEMETRY: HardwareTelemetry = {
  cpuUsage: 18.4,
  cpuTemp: 44.2,
  cpuClockGhz: 4.85,
  memoryUsedGb: 12.8,
  memoryTotalGb: 64.0,
  vramUsedGb: 6.2,
  vramTotalGb: 24.0,
  gpuName: 'NVIDIA RTX 4090 (24GB VRAM)',
  diskUsedGb: 412,
  diskTotalGb: 2048,
  diskIoRateMb: 34.6,
  uptimeSeconds: 84620,
  heartbeatLatencyMs: 98,
  history: {
    cpu: [12, 14, 18, 22, 19, 15, 17, 24, 21, 18],
    memory: [20, 20, 21, 20, 20, 21, 21, 20, 20, 20],
    vram: [25, 25, 26, 26, 25, 27, 26, 25, 26, 26],
  },
};

export const INITIAL_CONVERSATIONS: Conversation[] = [
  {
    id: 'conv-001',
    title: 'Diagnóstico & Refatoração de Auth em FnCash',
    createdAt: new Date(Date.now() - 3600000 * 2).toISOString(),
    updatedAt: new Date(Date.now() - 60000 * 5).toISOString(),
    messageCount: 8,
    status: 'active',
    lastMessageSnippet: 'Analisei a árvore de tokens JWT e preparei a correção com validação de expiração.',
  },
  {
    id: 'conv-002',
    title: 'Otimização de Query PostgreSQL e Índices',
    createdAt: new Date(Date.now() - 86400000).toISOString(),
    updatedAt: new Date(Date.now() - 86400000 + 7200000).toISOString(),
    messageCount: 12,
    status: 'archived',
    lastMessageSnippet: 'Índices compostos criados com sucesso na tabela de transações.',
  },
  {
    id: 'conv-003',
    title: 'Automação de Backup S3 do Workspace',
    createdAt: new Date(Date.now() - 86400000 * 3).toISOString(),
    updatedAt: new Date(Date.now() - 86400000 * 3 + 3600000).toISOString(),
    messageCount: 5,
    status: 'archived',
    lastMessageSnippet: 'Script rsync e criptografia GPG configurados.',
  },
];

export const INITIAL_MESSAGES: Record<string, ChatMessage[]> = {
  'conv-001': [
    {
      id: 'msg-01',
      conversationId: 'conv-001',
      role: 'user',
      content: 'Odin, identifiquei um problema de expiração de token na rota `/api/v1/auth/refresh` do projeto FnCash. Pode analisar o código e verificar por que as sessões estão sendo deslogadas antes do prazo?',
      timestamp: new Date(Date.now() - 3600000 * 2).toISOString(),
    },
    {
      id: 'msg-02',
      conversationId: 'conv-001',
      role: 'assistant',
      content: 'Iniciando inspeção do workspace no projeto FnCash. Vou ler o controller de autenticação e os middlewares de verificação de token para rastrear o cálculo do TTL.',
      timestamp: new Date(Date.now() - 3600000 * 2 + 3000).toISOString(),
      tokenMetrics: { tokensUsed: 420, tokensPerSec: 48, latencyMs: 310 },
      toolCalls: [
        {
          id: 'tool-01',
          toolName: 'read_file',
          operation: 'READ',
          args: { path: '/home/caua/odin-workspace/projects/FnCash/src/auth/jwt.service.ts' },
          status: 'success',
          executionTimeMs: 42,
          output: 'Arquivo jwt.service.ts lido com sucesso (148 linhas).',
        },
        {
          id: 'tool-02',
          toolName: 'analyze_ast',
          operation: 'READ',
          args: { target: 'validateRefreshToken', file: 'jwt.service.ts' },
          status: 'success',
          executionTimeMs: 115,
          output: 'Encontrada inconsistência: TTL do refresh_token comparado em milissegundos com timestamp em segundos (epoch mismatch).',
        },
      ],
    },
    {
      id: 'msg-03',
      conversationId: 'conv-001',
      role: 'assistant',
      content: `Encontrei a causa raiz do problema. No método \`validateRefreshToken\`, o timestamp de expiração do JWT está sendo retornado em **segundos** (\`exp\`), porém a validação está subtraindo diretamente de \`Date.now()\` (que retorna **milissegundos**).
      
Isso faz com que o token pareça ter expirado em 1970 logo no primeiro refresh.

Preparei o patch de correção. Como esta ação modifica o disco local, solicitei sua autorização formal via política Zero-Trust:`,
      timestamp: new Date(Date.now() - 3600000 * 2 + 7000).toISOString(),
      tokenMetrics: { tokensUsed: 890, tokensPerSec: 52, latencyMs: 450 },
      toolCalls: [
        {
          id: 'tool-03',
          toolName: 'write_file',
          operation: 'WRITE',
          args: {
            path: '/home/caua/odin-workspace/projects/FnCash/src/auth/jwt.service.ts',
            lines: '78-85',
          },
          status: 'pending',
          diffSnippet: `@@ -78,7 +78,7 @@
-  const nowInSec = Date.now(); // Bug: Retorna ms ao invés de segundos
+  const nowInSec = Math.floor(Date.now() / 1000);
   if (decoded.exp < nowInSec) {
     throw new UnauthorizedException('Refresh token expired');
   }`,
        },
      ],
      approvalRequest: {
        id: 'appr-001',
        conversationId: 'conv-001',
        tool: 'write_file',
        operation: 'WRITE',
        permissionState: 'REQUIRES_APPROVAL',
        target: '/home/caua/odin-workspace/projects/FnCash/src/auth/jwt.service.ts',
        reason: 'Aplicar patch corrigindo discrepância de unidades de tempo (ms vs seg) na validação de TTL do refresh token.',
        riskLevel: 'medium',
        status: 'pending',
        requestedAt: new Date(Date.now() - 60000 * 15).toISOString(),
        diffPreview: `- const nowInSec = Date.now();\n+ const nowInSec = Math.floor(Date.now() / 1000);`,
      },
    },
  ],
};

export const INITIAL_APPROVALS: ApprovalItem[] = [
  {
    id: 'appr-001',
    conversationId: 'conv-001',
    tool: 'write_file',
    operation: 'WRITE',
    permissionState: 'REQUIRES_APPROVAL',
    target: '/home/caua/odin-workspace/projects/FnCash/src/auth/jwt.service.ts',
    reason: 'Aplicar patch de correção de TTL de autenticação JWT',
    riskLevel: 'medium',
    status: 'pending',
    requestedAt: new Date(Date.now() - 60000 * 15).toISOString(),
    diffPreview: `@@ -78,7 +78,7 @@\n- const nowInSec = Date.now();\n+ const nowInSec = Math.floor(Date.now() / 1000);`,
  },
  {
    id: 'appr-002',
    conversationId: 'conv-001',
    tool: 'execute_command',
    operation: 'DELETE',
    permissionState: 'REQUIRES_APPROVAL',
    target: '/home/caua/odin-workspace/projects/FnCash/tmp/cache_dump.lock',
    reason: 'Remover lockfile corrompido de cache Redis detectado durante o diagnóstico do ambiente local.',
    riskLevel: 'high',
    status: 'pending',
    requestedAt: new Date(Date.now() - 60000 * 8).toISOString(),
    commandPreview: 'rm -f /home/caua/odin-workspace/projects/FnCash/tmp/cache_dump.lock',
  },
  {
    id: 'appr-003',
    conversationId: 'conv-002',
    tool: 'execute_command',
    operation: 'EXECUTE',
    permissionState: 'ALLOWED',
    target: 'psql -d fncash_dev -c "CREATE INDEX idx_transactions_created..."',
    reason: 'Criar índices de performance na base de desenvolvimento local',
    riskLevel: 'medium',
    status: 'approved',
    requestedAt: new Date(Date.now() - 86400000).toISOString(),
    resolvedAt: new Date(Date.now() - 86400000 + 45000).toISOString(),
    resolvedBy: 'Operator (Cauã)',
    commandPreview: 'psql -U postgres -d fncash_dev -f /workspace/scripts/add_index.sql',
  },
  {
    id: 'appr-004',
    conversationId: 'conv-003',
    tool: 'execute_command',
    operation: 'DELETE',
    permissionState: 'DENIED',
    target: 'rm -rf /var/log/syslog.old',
    reason: 'Limpeza de logs de sistema externo à pasta do workspace',
    riskLevel: 'critical',
    status: 'rejected',
    requestedAt: new Date(Date.now() - 86400000 * 2).toISOString(),
    resolvedAt: new Date(Date.now() - 86400000 * 2 + 120000).toISOString(),
    resolvedBy: 'Operator (Cauã)',
    commandPreview: 'rm -rf /var/log/syslog.old',
  },
];

export const INITIAL_ACTIVITIES: Activity[] = [
  {
    id: 'act-001',
    title: 'Auditoria de Vulnerabilidade AST',
    description: 'Análise léxica e sintática de arquivos de auth no módulo FnCash/src/auth.',
    type: 'TOOL_EXEC',
    status: 'completed',
    startedAt: new Date(Date.now() - 60000 * 25).toISOString(),
    completedAt: new Date(Date.now() - 60000 * 24).toISOString(),
    durationMs: 115,
    result: 'Bug de epoch unit localizado no método validateRefreshToken na linha 78.',
    details: {
      path: '/home/caua/odin-workspace/projects/FnCash/src/auth/jwt.service.ts',
      stdout: '[AST_PARSER] Parsed 148 nodes in 115ms. 0 syntax errors. Found logic warning: timestamp scale mismatch.',
    },
  },
  {
    id: 'act-002',
    title: 'Solicitação de Autorização Zero-Trust',
    description: 'Ação crítica de modificação de arquivo travada aguardando assinatura do operador.',
    type: 'SECURITY_CHECK',
    status: 'waiting_approval',
    startedAt: new Date(Date.now() - 60000 * 15).toISOString(),
    durationMs: undefined,
    result: 'Fila de aprovação ID #appr-001 disparada com sucesso.',
    details: {
      path: '/home/caua/odin-workspace/projects/FnCash/src/auth/jwt.service.ts',
      command: 'write_file --dry-run',
      diff: '- const nowInSec = Date.now();\n+ const nowInSec = Math.floor(Date.now() / 1000);',
    },
  },
  {
    id: 'act-003',
    title: 'Limpeza de Lockfile Redis',
    description: 'Tentativa de exclusão de lock de processo residual corrompido.',
    type: 'COMMAND',
    status: 'waiting_approval',
    startedAt: new Date(Date.now() - 60000 * 8).toISOString(),
    details: {
      command: 'rm -f /home/caua/odin-workspace/projects/FnCash/tmp/cache_dump.lock',
      path: '/tmp/cache_dump.lock',
    },
  },
  {
    id: 'act-004',
    title: 'Sincronização de Threads de Inferência',
    description: 'Verificação periódica de heartbeat do motor de IA e alocação de pool.',
    type: 'THREAD_SYNC',
    status: 'completed',
    startedAt: new Date(Date.now() - 60000 * 3).toISOString(),
    completedAt: new Date(Date.now() - 60000 * 3 + 98).toISOString(),
    durationMs: 98,
    result: 'Heartbeat OK (98ms latency). Conexão ativa com Claude 3.7 & Gemini 2.5.',
  },
  {
    id: 'act-005',
    title: 'Indexação de Arquivos do Workspace',
    description: 'Varredura de repositórios Git no workspace para mapeamento de símbolos LSP.',
    type: 'FILESYSTEM',
    status: 'completed',
    startedAt: new Date(Date.now() - 3600000).toISOString(),
    completedAt: new Date(Date.now() - 3600000 + 1420).toISOString(),
    durationMs: 1420,
    result: '1.240 arquivos indexados em 4 sub-projetos com árvore de dependências atualizada.',
  },
  {
    id: 'act-006',
    title: 'Execução de Testes Unitários de Regressão',
    description: 'Executado Jest para módulo de pagamentos e split de transações.',
    type: 'TOOL_EXEC',
    status: 'completed',
    startedAt: new Date(Date.now() - 7200000).toISOString(),
    completedAt: new Date(Date.now() - 7200000 + 4300).toISOString(),
    durationMs: 4300,
    result: 'PASS: 34 testes concluídos, 0 falhas.',
    details: {
      command: 'pnpm test:unit --filter=payments',
      stdout: 'PASS src/payments/transfer.spec.ts (1.8s)\nPASS src/payments/split.spec.ts (1.2s)\n\nTest Suites: 2 passed, 2 total\nTests: 34 passed, 34 total',
    },
  },
];

export const INITIAL_WORKSPACE_TREE: FileNode[] = [
  {
    id: 'node-root-projects',
    name: 'projects',
    path: '/workspace/projects',
    type: 'directory',
    updatedAt: new Date(Date.now() - 3600000).toISOString(),
    children: [
      {
        id: 'node-fncash',
        name: 'FnCash',
        path: '/workspace/projects/FnCash',
        type: 'directory',
        updatedAt: new Date(Date.now() - 3600000).toISOString(),
        children: [
          {
            id: 'node-fncash-src',
            name: 'src',
            path: '/workspace/projects/FnCash/src',
            type: 'directory',
            updatedAt: new Date(Date.now() - 3600000).toISOString(),
            children: [
              {
                id: 'node-fncash-auth',
                name: 'auth',
                path: '/workspace/projects/FnCash/src/auth',
                type: 'directory',
                updatedAt: new Date(Date.now() - 60000 * 15).toISOString(),
                children: [
                  {
                    id: 'node-fncash-jwt',
                    name: 'jwt.service.ts',
                    path: '/workspace/projects/FnCash/src/auth/jwt.service.ts',
                    type: 'file',
                    size: 4820,
                    extension: 'ts',
                    updatedAt: new Date(Date.now() - 60000 * 15).toISOString(),
                    modifiedByOdin: true,
                    lastChangeSummary: 'Patch pendente: correção de unidade de tempo no TTL',
                    content: `import { Injectable, UnauthorizedException } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { UserSession } from './types';

@Injectable()
export class TokenService {
  constructor(private readonly jwt: JwtService) {}

  async generateTokens(session: UserSession) {
    const payload = { sub: session.userId, email: session.email, role: session.role };
    
    const accessToken = await this.jwt.signAsync(payload, { expiresIn: '15m' });
    const refreshToken = await this.jwt.signAsync(payload, { expiresIn: '7d' });

    return { accessToken, refreshToken };
  }

  async validateRefreshToken(token: string): Promise<boolean> {
    try {
      const decoded = await this.jwt.verifyAsync(token);
      
      // BUG FIX: Comparação em segundos inteiros
      const nowInSec = Math.floor(Date.now() / 1000);
      
      if (decoded.exp && decoded.exp < nowInSec) {
        throw new UnauthorizedException('Refresh token expirado');
      }

      return true;
    } catch (err) {
      throw new UnauthorizedException('Token inválido ou corrompido');
    }
  }
}
`,
                  },
                  {
                    id: 'node-fncash-auth-guard',
                    name: 'auth.guard.ts',
                    path: '/workspace/projects/FnCash/src/auth/auth.guard.ts',
                    type: 'file',
                    size: 2150,
                    extension: 'ts',
                    updatedAt: new Date(Date.now() - 86400000).toISOString(),
                    content: `import { CanActivate, ExecutionContext, Injectable } from '@nestjs/common';

@Injectable()
export class AuthGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const req = context.switchToHttp().getRequest();
    return !!req.headers.authorization;
  }
}
`,
                  },
                ],
              },
              {
                id: 'node-fncash-main',
                name: 'main.ts',
                path: '/workspace/projects/FnCash/src/main.ts',
                type: 'file',
                size: 1420,
                extension: 'ts',
                updatedAt: new Date(Date.now() - 86400000 * 2).toISOString(),
                content: `import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.enableCors();
  await app.listen(4000);
  console.log('FnCash API online na porta 4000');
}
bootstrap();
`,
              },
            ],
          },
          {
            id: 'node-fncash-package',
            name: 'package.json',
            path: '/workspace/projects/FnCash/package.json',
            type: 'file',
            size: 890,
            extension: 'json',
            updatedAt: new Date(Date.now() - 86400000 * 3).toISOString(),
            content: `{\n  "name": "fncash-api",\n  "version": "1.4.0",\n  "dependencies": {\n    "@nestjs/core": "^10.0.0",\n    "@nestjs/jwt": "^10.1.0"\n  }\n}`,
          },
        ],
      },
    ],
  },
  {
    id: 'node-documents',
    name: 'documents',
    path: '/workspace/documents',
    type: 'directory',
    updatedAt: new Date(Date.now() - 86400000 * 5).toISOString(),
    children: [
      {
        id: 'node-arch-spec',
        name: 'architecture_spec.md',
        path: '/workspace/documents/architecture_spec.md',
        type: 'file',
        size: 5320,
        extension: 'md',
        updatedAt: new Date(Date.now() - 86400000 * 2).toISOString(),
        content: `# Odin Architecture Specification\n\nO assistente segue padrão de supervisão de agentes com barreira zero-trust de segurança local.`,
      },
      {
        id: 'node-env-notes',
        name: 'env_configs.json',
        path: '/workspace/documents/env_configs.json',
        type: 'file',
        size: 1040,
        extension: 'json',
        updatedAt: new Date(Date.now() - 86400000 * 4).toISOString(),
        content: `{\n  "environment": "development",\n  "local_node": "ODIN_01",\n  "sandbox": true\n}`,
      },
    ],
  },
  {
    id: 'node-scripts',
    name: 'scripts',
    path: '/workspace/scripts',
    type: 'directory',
    updatedAt: new Date(Date.now() - 86400000 * 2).toISOString(),
    children: [
      {
        id: 'node-backup-script',
        name: 'backup_workspace.sh',
        path: '/workspace/scripts/backup_workspace.sh',
        type: 'file',
        size: 920,
        extension: 'sh',
        updatedAt: new Date(Date.now() - 86400000).toISOString(),
        content: `#!/usr/bin/env bash\n# Script de backup automatizado Odin\ntar -czf /backups/odin_$(date +%Y%m%d).tar.gz /home/caua/odin-workspace\necho "Backup concluído."`,
      },
    ],
  },
  {
    id: 'node-readme',
    name: 'README.md',
    path: '/workspace/README.md',
    type: 'file',
    size: 2180,
    extension: 'md',
    updatedAt: new Date(Date.now() - 86400000 * 10).toISOString(),
    modifiedByOdin: true,
    lastChangeSummary: 'Estrutura de diretórios documentada e linkada',
    content: `# ODIN Workspace\n\nDiretório raiz monitorado pelo assistente Odin com proteção de leitura/escrita supervisionada.`,
  },
];

export const INITIAL_MEMORIES: MemoryItem[] = [
  {
    id: 'mem-001',
    key: 'Nome do Operador',
    value: 'Cauã (Software Engineer & AI Architect)',
    category: 'User',
    confidence: 1.0,
    tags: ['identidade', 'preferencia', 'operador'],
    createdAt: new Date(Date.now() - 86400000 * 30).toISOString(),
    updatedAt: new Date(Date.now() - 86400000 * 2).toISOString(),
    isPinned: true,
  },
  {
    id: 'mem-002',
    key: 'Stack Principal',
    value: 'TypeScript / Next.js, FastAPI / Python, Tailwind CSS, PostgreSQL, Docker, PyTorch local.',
    category: 'Preferences',
    confidence: 0.98,
    tags: ['tech-stack', 'desenvolvimento', 'frameworks'],
    createdAt: new Date(Date.now() - 86400000 * 20).toISOString(),
    updatedAt: new Date(Date.now() - 86400000 * 5).toISOString(),
    isPinned: true,
  },
  {
    id: 'mem-003',
    key: 'Projeto Ativo: FnCash',
    value: 'Plataforma financeira local com autenticação JWT e isolamento de tenant em Postgres.',
    category: 'Projects',
    confidence: 0.95,
    tags: ['fncash', 'financeiro', 'nest-js', 'jwt'],
    createdAt: new Date(Date.now() - 86400000 * 10).toISOString(),
    updatedAt: new Date(Date.now() - 3600000 * 2).toISOString(),
    isPinned: true,
  },
  {
    id: 'mem-004',
    key: 'Política de Modificação de Disco',
    value: 'Nunca executar comandos `rm` ou `write_file` em arquivos fora de `/workspace` sem aprovação prévia.',
    category: 'Knowledge',
    confidence: 1.0,
    tags: ['seguranca', 'zero-trust', 'regras-criticas'],
    createdAt: new Date(Date.now() - 86400000 * 15).toISOString(),
    updatedAt: new Date(Date.now() - 86400000 * 15).toISOString(),
    isPinned: true,
  },
  {
    id: 'mem-005',
    key: 'Preferencia de Resposta',
    value: 'Respostas técnicas diretas, com trechos de código formatados e diffs explícitos quando houver refatoração.',
    category: 'Preferences',
    confidence: 0.96,
    tags: ['comunicacao', 'formato', 'codigo'],
    createdAt: new Date(Date.now() - 86400000 * 25).toISOString(),
    updatedAt: new Date(Date.now() - 86400000 * 12).toISOString(),
  },
  {
    id: 'mem-006',
    key: 'Sessão Atual de Depuração',
    value: 'Investigação em andamento no bug de TTL de token JWT do FnCash.',
    category: 'Context',
    confidence: 0.99,
    tags: ['sessao', 'fncash', 'jwt-bug'],
    createdAt: new Date(Date.now() - 3600000 * 3).toISOString(),
    updatedAt: new Date(Date.now() - 60000 * 10).toISOString(),
  },
  {
    id: 'mem-007',
    key: 'Tarefa Agendada: Backup Semanal',
    value: 'Executar `/workspace/scripts/backup_workspace.sh` todo domingo às 03:00 UTC.',
    category: 'Tasks',
    confidence: 0.92,
    tags: ['cron', 'backup', 'automacao'],
    createdAt: new Date(Date.now() - 86400000 * 7).toISOString(),
    updatedAt: new Date(Date.now() - 86400000 * 7).toISOString(),
  },
];

export const INITIAL_REGISTERED_TOOLS: RegisteredTool[] = [
  { id: 'tool-fs-read', name: 'read_file', category: 'filesystem', description: 'Lê o conteúdo completo ou parcial de arquivos do disco.', riskLevel: 'low', operationType: 'READ', enabled: true, requiresApproval: false },
  { id: 'tool-fs-write', name: 'write_file', category: 'filesystem', description: 'Grava ou modifica conteúdo em arquivos do disco.', riskLevel: 'medium', operationType: 'WRITE', enabled: true, requiresApproval: true },
  { id: 'tool-fs-list', name: 'list_directory', category: 'filesystem', description: 'Navega e indexa a árvore de diretórios do workspace.', riskLevel: 'low', operationType: 'READ', enabled: true, requiresApproval: false },
  { id: 'tool-sh-exec', name: 'execute_command', category: 'shell', description: 'Executa comandos bash isolados no ambiente local.', riskLevel: 'high', operationType: 'EXECUTE', enabled: true, requiresApproval: true },
  { id: 'tool-code-ast', name: 'analyze_ast', category: 'code_intelligence', description: 'Gera AST sintática e localiza referências de variáveis/funções.', riskLevel: 'low', operationType: 'READ', enabled: true, requiresApproval: false },
  { id: 'tool-git-diff', name: 'git_diff', category: 'version_control', description: 'Compara alterações com branches ou commits do Git.', riskLevel: 'low', operationType: 'READ', enabled: true, requiresApproval: false },
  { id: 'tool-net-fetch', name: 'fetch_url', category: 'network', description: 'Realiza requisições HTTP para consultar documentações externas.', riskLevel: 'medium', operationType: 'EXTERNAL_ACTION', enabled: true, requiresApproval: false },
];

export const INITIAL_SKILLS: SkillModule[] = [
  { id: 'skill-code-audit', name: 'Code Auditor & Refactorer', version: '2.1.0', description: 'Especialista em análise de código estático, refatoração e detecção de bugs em TypeScript/Python.', status: 'active', triggers: ['refactor', 'analise', 'bug', 'fix'] },
  { id: 'skill-devops', name: 'DevOps & Environment Automation', version: '1.4.0', description: 'Automação de scripts bash, Dockerfiles e pipelines locais de CI/CD.', status: 'active', triggers: ['docker', 'deploy', 'script', 'bash'] },
  { id: 'skill-db-optimizer', name: 'Database Query Optimizer', version: '1.2.0', description: 'Análise de planos de execução SQL (EXPLAIN ANALYZE) e sugestão de índices.', status: 'standby', triggers: ['sql', 'query', 'postgres', 'index'] },
];

export const INITIAL_MCP_SERVERS: McpServer[] = [
  { id: 'mcp-local-fs', name: 'odin-filesystem-mcp', transport: 'stdio', endpoint: 'local::process::odin-fs', status: 'connected', latencyMs: 2, toolsCount: 5 },
  { id: 'mcp-git-bridge', name: 'git-bridge-mcp', transport: 'stdio', endpoint: 'local::process::git-mcp', status: 'connected', latencyMs: 4, toolsCount: 4 },
  { id: 'mcp-browser', name: 'browser-context-mcp', transport: 'sse', endpoint: 'http://127.0.0.1:9090/sse', status: 'connected', latencyMs: 18, toolsCount: 3 },
];

export const INITIAL_SETTINGS: OdinSettings = {
  general: {
    assistantName: 'Odin',
    language: 'pt-BR',
    theme: 'tactical',
    notificationsEnabled: true,
    soundFeedback: false,
    streamTokens: true,
    workspacePath: '/home/caua/odin-workspace',
  },
  ai: {
    provider: 'gemini',
    primaryModel: 'gemini-2.5-flash',
    fallbackModel: 'qwen2.5-coder:14b-local',
    temperature: 0.2,
    maxTokens: 8192,
    topP: 0.95,
    autoFallbackEnabled: true,
    systemPromptAdditions: 'Priorize sempre segurança zero-trust e respostas diretas e precisas.',
  },
  security: {
    zeroTrustMode: true,
    workspaceBoundaryStrict: true,
    allowDestructiveCommandsWithoutConfirm: false,
    auditLoggingEnabled: true,
    autoExpireApprovalsMinutes: 30,
  },
  system: {
    version: '1.0.0-MVP',
    backendUrl: 'http://127.0.0.1:8000',
    websocketUrl: 'ws://127.0.0.1:8000/ws',
    mockMode: true,
  },
};
