export interface ToolParameterSchema {
  type: string;
  properties: Record<string, ToolParameterProperty>;
  required?: string[];
}

export interface ToolParameterProperty {
  type: string;
  description?: string;
  default?: unknown;
  enum?: string[];
}

export interface ToolDefinition {
  name: string;
  description: string;
  category: string;
  requires_approval_by_default: boolean;
  parameters_schema: ToolParameterSchema;
}

export interface ToolCategory {
  category: string;
  tools: ToolDefinition[];
}