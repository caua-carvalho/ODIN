const API_BASE = import.meta.env.VITE_API_URL || '';

class ApiError extends Error {
  readonly status: number;
  readonly statusText: string;

  constructor(status: number, statusText: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.statusText = statusText;
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    let message = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const errorData = await response.json();
      if (errorData.detail) {
        message = Array.isArray(errorData.detail) 
          ? errorData.detail.map((d: { msg?: string; message?: string }) => d.msg || d.message || JSON.stringify(d)).join(', ')
          : errorData.detail;
      }
    } catch {
      // Use default message
    }
    throw new ApiError(response.status, response.statusText, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

export const api = {
  get: <T>(endpoint: string) => request<T>(endpoint, { method: 'GET' }),
  post: <T>(endpoint: string, data: unknown) => request<T>(endpoint, { 
    method: 'POST', 
    body: JSON.stringify(data) 
  }),
  delete: <T>(endpoint: string) => request<T>(endpoint, { method: 'DELETE' }),
};

export { ApiError };