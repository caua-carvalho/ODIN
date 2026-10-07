export type PermissionRiskLevel = 'low' | 'medium' | 'high' | 'critical';
export type PermissionStatus = 'pending' | 'approved' | 'denied' | 'expired';

export interface PermissionRequest {
  id: string;
  conversation_id: string;
  tool: string;
  operation: string;
  arguments_json: string;
  target: string;
  reason: string;
  risk_level: PermissionRiskLevel;
  status: PermissionStatus;
  created_at: string;
  resolved_at: string | null;
}

export interface PermissionActionResponse {
  id: string;
  status: PermissionStatus;
}