// Fetch wrapper for the MVP's /api/* (mvp/app/main.py).
// - Same-origin cookie, JSON in and out; errors arrive as JSON `{error: '<화면에 보여도 되는 글>', ...}`.
// - 401 with `need_login` (no session, expired, or the app was restarted) sends the user to
//   /login. A wrong password is also 401 but without `need_login`; it stays with its form.
// - A request that gets no response at all is a NetworkError.

export interface ApiErrorBody {
  error: string;
  need_login?: boolean;
  tries_left?: number;
  locked_for?: number;
  kind?: string;
  problems?: unknown[];
  title?: string;
  detail?: string;
}

export class ApiError extends Error {
  readonly status: number;
  /** The JSON body as sent (message plus extras like `tries_left` or `locked_for`). */
  readonly body: ApiErrorBody | null;

  constructor(status: number, body: ApiErrorBody | null) {
    super(body?.error ?? `http-${String(status)}`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

/** No response: the app is not running, or the connection dropped. */
export class NetworkError extends Error {
  constructor(error: unknown) {
    super('network', { cause: error });
    this.name = 'NetworkError';
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

interface ClientConfig {
  fetch: typeof fetch;
  /** Called when the server says the session is gone. */
  onLoginRequired: () => void;
}

const defaults: ClientConfig = {
  fetch: (input, init) => globalThis.fetch(input, init),
  onLoginRequired: () => {
    window.location.assign('/login');
  },
};

const config: ClientConfig = { ...defaults };

export function configureClient(next: Partial<ClientConfig>): void {
  Object.assign(config, next);
}

export function resetClient(): void {
  Object.assign(config, defaults);
}

export type QueryValue = string | number | boolean | null | undefined;

export function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as { error?: unknown }).error === 'string'
  );
}

export async function request<T>(
  method: 'GET' | 'POST' | 'PUT' | 'DELETE',
  path: string,
  options: { query?: Record<string, QueryValue> | undefined; body?: unknown } = {},
): Promise<T> {
  const { query, body } = options;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined || method === 'POST') headers['Content-Type'] = 'application/json';

  let res: Response;
  try {
    res = await config.fetch(buildUrl(path, query), {
      method,
      credentials: 'same-origin',
      headers,
      body: body === undefined ? (method === 'POST' ? '{}' : null) : JSON.stringify(body),
    });
  } catch (error) {
    throw new NetworkError(error);
  }

  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      throw new ApiError(res.status, null);
    }
  }
  if (!res.ok) {
    const errorBody = isErrorBody(data) ? data : null;
    if (res.status === 401 && errorBody?.need_login) config.onLoginRequired();
    throw new ApiError(res.status, errorBody);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, query?: Record<string, QueryValue>) => request<T>('GET', path, { query }),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, { body }),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, { body }),
  delete: <T>(path: string) => request<T>('DELETE', path),
};
