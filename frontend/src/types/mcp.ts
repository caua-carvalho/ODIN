export interface MCPServer {
  name: string;
  description: string;
  status: 'connected' | 'disconnected' | 'error';
  tool_count: number;
  url: string | null;
}