export interface BaseEvent {
  type: string;
}

export interface StatusEvent extends BaseEvent {
  type: 'status';
  message: string;
}

export interface TextChunkEvent extends BaseEvent {
  type: 'text_chunk';
  content: string;
}

export interface ToolStartEvent extends BaseEvent {
  type: 'tool_start';
  tool: string;
  tool_call_id: string;
  arguments: Record<string, unknown>;
}

export interface ToolEndEvent extends BaseEvent {
  type: 'tool_end';
  tool: string;
  tool_call_id: string;
  success: boolean;
  result: Record<string, unknown>;
}

export interface PermissionRequestEvent extends BaseEvent {
  type: 'permission_request';
  id: string;
  tool: string;
  operation: string;
  target: string;
  reason: string;
  risk_level: string;
  arguments: Record<string, unknown>;
}

export interface PermissionResolvedEvent extends BaseEvent {
  type: 'permission_resolved';
  id: string;
  approved: boolean;
}

export interface DoneEvent extends BaseEvent {
  type: 'done';
  conversation_id: string;
}

export interface ErrorEvent extends BaseEvent {
  type: 'error';
  message: string;
}

export interface PongEvent extends BaseEvent {
  type: 'pong';
}

export type OdinEvent =
  | StatusEvent
  | TextChunkEvent
  | ToolStartEvent
  | ToolEndEvent
  | PermissionRequestEvent
  | PermissionResolvedEvent
  | DoneEvent
  | ErrorEvent
  | PongEvent;

export interface ClientMessage {
  type: 'message' | 'ping';
  content?: string;
}