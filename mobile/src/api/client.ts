import { absoluteUrl, getClientConfig } from '../lib/config';

export class ApiError extends Error {
  readonly status: number;
  readonly statusText: string;

  constructor(status: number, statusText: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.statusText = statusText;
  }
}

function authHeaders(): Record<string, string> {
  const token = getClientConfig()?.token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let message = `HTTP ${response.status}: ${response.statusText}`;
    try {
      const errorData: unknown = await response.json();
      if (typeof errorData === 'object' && errorData !== null && 'detail' in errorData) {
        const detail = (errorData as { detail: unknown }).detail;
        if (Array.isArray(detail)) {
          message = detail
            .map((d) => {
              const item = d as { msg?: string; message?: string };
              return item.msg || item.message || JSON.stringify(d);
            })
            .join(', ');
        } else if (typeof detail === 'string') {
          message = detail;
        }
      }
    } catch {
      // Fall back to the default message.
    }
    throw new ApiError(response.status, response.statusText, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(absoluteUrl(endpoint), {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...(options.headers as Record<string, string> | undefined),
    },
  });
  return parseResponse<T>(response);
}

export const api = {
  get: <T>(endpoint: string) => request<T>(endpoint, { method: 'GET' }),
  post: <T>(endpoint: string, data: unknown) =>
    request<T>(endpoint, { method: 'POST', body: JSON.stringify(data) }),
  patch: <T>(endpoint: string, data: unknown) =>
    request<T>(endpoint, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: <T>(endpoint: string) => request<T>(endpoint, { method: 'DELETE' }),
};

/**
 * Multipart upload. On React Native, file entries are `{ uri, name, type }`
 * objects appended to a FormData.
 */
export async function upload<T>(endpoint: string, formData: FormData): Promise<T> {
  const response = await fetch(absoluteUrl(endpoint), {
    method: 'POST',
    body: formData,
    headers: authHeaders(),
  });
  return parseResponse<T>(response);
}