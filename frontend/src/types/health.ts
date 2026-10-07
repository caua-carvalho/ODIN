export interface HealthResponse {
  status: 'online' | 'offline';
  version: string;
  model_provider: string;
  model: string;
  workspace: string;
  tools_count: number;
  agent_ready: boolean;
}