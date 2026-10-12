const API_BASE = import.meta.env.VITE_API_URL || '';

/**
 * Optional API token for the mobile/remote clients.
 *
 * Set `localStorage['odin_api_token']` (e.g. in the browser console:
 * `localStorage.setItem('odin_api_token', '<token>')`) to authenticate every
 * API/WebSocket request once the backend has ODIN_API_TOKEN enabled.
 */
export function getApiToken(): string {
  try {
    return window.localStorage.getItem('odin_api_token') || '';
  } catch {
    return '';
  }
}

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

async function parseResponse<T>(response: Response): Promise<T> {
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

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${endpoint}`;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> | undefined),
  };
  const token = getApiToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(url, {
    ...options,
    headers,
  });

  return parseResponse<T>(response);
}

/** Upload a multipart body. Content-Type is set by the browser (boundary). */
async function upload<T>(endpoint: string, formData: FormData): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getApiToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    body: formData,
    headers,
  });
  return parseResponse<T>(response);
}

export const api = {
  get: <T>(endpoint: string) => request<T>(endpoint, { method: 'GET' }),
  post: <T>(endpoint: string, data: unknown) => request<T>(endpoint, {
    method: 'POST',
    body: JSON.stringify(data)
  }),
  patch: <T>(endpoint: string, data: unknown) => request<T>(endpoint, {
    method: 'PATCH',
    body: JSON.stringify(data)
  }),
  delete: <T>(endpoint: string) => request<T>(endpoint, { method: 'DELETE' }),
};

export { ApiError, upload, API_BASE };
