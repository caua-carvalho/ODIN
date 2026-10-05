import { OdinAgentState, ActivityStatus, RiskLevel, OperationType } from '../types';

export const AGENT_STATE_CONFIG: Record<
  OdinAgentState,
  {
    label: string;
    description: string;
    color: string;
    bgColor: string;
    borderColor: string;
    glowClass: string;
    iconSymbol: string;
  }
> = {
  IDLE: {
    label: 'IDLE / PRONTO',
    description: 'Odin está em standby pronto para novas ordens.',
    color: 'text-emerald-400',
    bgColor: 'bg-emerald-500/10',
    borderColor: 'border-emerald-500/30',
    glowClass: 'shadow-[0_0_15px_-3px_rgba(16,185,129,0.3)]',
    iconSymbol: '●',
  },
  THINKING: {
    label: 'PENSANDO...',
    description: 'Analisando o contexto e planejando a sequência de passos.',
    color: 'text-sky-400',
    bgColor: 'bg-sky-500/10',
    borderColor: 'border-sky-500/30',
    glowClass: 'shadow-[0_0_15px_-3px_rgba(56,189,248,0.35)]',
    iconSymbol: '◌',
  },
  EXECUTING: {
    label: 'EXECUTANDO FERRAMENTA',
    description: 'Processando sub-rotina ou chamada RPC no sistema.',
    color: 'text-odin-primary',
    bgColor: 'bg-odin-primary/10',
    borderColor: 'border-odin-primary/40',
    glowClass: 'shadow-[0_0_18px_-2px_rgba(255,122,0,0.4)]',
    iconSymbol: '⚡',
  },
  WAITING_APPROVAL: {
    label: 'AÇÃO REQUER APROVAÇÃO',
    description: 'Pausa de segurança: autorização do operador necessária.',
    color: 'text-amber-400',
    bgColor: 'bg-amber-500/15',
    borderColor: 'border-amber-500/50',
    glowClass: 'shadow-[0_0_20px_-2px_rgba(245,158,11,0.45)]',
    iconSymbol: '⚠',
  },
  COMPLETED: {
    label: 'CONCLUÍDO',
    description: 'Todas as tarefas solicitadas foram finalizadas com sucesso.',
    color: 'text-emerald-400',
    bgColor: 'bg-emerald-500/10',
    borderColor: 'border-emerald-500/30',
    glowClass: 'shadow-[0_0_15px_-3px_rgba(16,185,129,0.3)]',
    iconSymbol: '✓',
  },
  ERROR: {
    label: 'FALHA NA EXECUÇÃO',
    description: 'Ocorreu um erro no processo ou na ferramenta executada.',
    color: 'text-rose-400',
    bgColor: 'bg-rose-500/15',
    borderColor: 'border-rose-500/40',
    glowClass: 'shadow-[0_0_20px_-2px_rgba(244,63,94,0.45)]',
    iconSymbol: '✕',
  },
};

export const ACTIVITY_STATUS_CONFIG: Record<
  ActivityStatus,
  { label: string; color: string; badgeVariant: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'secondary' }
> = {
  pending: { label: 'Pendente', color: 'text-zinc-400', badgeVariant: 'secondary' },
  running: { label: 'Em execução', color: 'text-odin-primary', badgeVariant: 'warning' },
  waiting_approval: { label: 'Aguardando Aprovação', color: 'text-amber-400', badgeVariant: 'warning' },
  completed: { label: 'Concluído', color: 'text-emerald-400', badgeVariant: 'success' },
  failed: { label: 'Falhou', color: 'text-rose-400', badgeVariant: 'danger' },
  cancelled: { label: 'Cancelado', color: 'text-zinc-500', badgeVariant: 'secondary' },
};

export const RISK_LEVEL_CONFIG: Record<
  RiskLevel,
  { label: string; color: string; bg: string; border: string }
> = {
  low: { label: 'Baixo Risco', color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/20' },
  medium: { label: 'Médio Risco', color: 'text-yellow-400', bg: 'bg-yellow-500/10', border: 'border-yellow-500/20' },
  high: { label: 'Alto Risco', color: 'text-orange-400', bg: 'bg-orange-500/15', border: 'border-orange-500/30' },
  critical: { label: 'Crítico / Destrutivo', color: 'text-rose-400', bg: 'bg-rose-500/20', border: 'border-rose-500/40' },
};

export const OPERATION_TYPE_CONFIG: Record<
  OperationType,
  { label: string; badgeClass: string; icon: string }
> = {
  READ: { label: 'READ', badgeClass: 'bg-blue-500/10 text-blue-400 border-blue-500/20', icon: 'FileText' },
  WRITE: { label: 'WRITE', badgeClass: 'bg-amber-500/10 text-amber-400 border-amber-500/20', icon: 'Edit3' },
  EXECUTE: { label: 'EXECUTE', badgeClass: 'bg-purple-500/10 text-purple-400 border-purple-500/20', icon: 'Terminal' },
  DELETE: { label: 'DELETE', badgeClass: 'bg-rose-500/15 text-rose-400 border-rose-500/30', icon: 'Trash2' },
  EXTERNAL_ACTION: { label: 'EXTERNAL', badgeClass: 'bg-orange-500/10 text-orange-400 border-orange-500/20', icon: 'Globe' },
};
