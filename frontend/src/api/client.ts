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

  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  return parseResponse<T>(response);
}

/** Upload a multipart body. Content-Type is set by the browser (boundary). */
async function upload<T>(endpoint: string, formData: FormData): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    body: formData,
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
