export interface HealthResponse {
  status: 'online' | 'offline';
  version: string;
  model_provider: string;
  model: string;
  workspace: string;
  tools_count: number;
  agent_ready: boolean;
  /** True when the backend requires an API token (login screen is shown). */
  auth_required: boolean;
}