// Fetch wrapper for /api/* (autotrade/CONTRACT.md).
// - Same-origin cookies, JSON in and out; errors arrive as JSON `{error, detail?}`.
// - 403 `session` (no cookie, expired or ended) sends the user to /pin and remembers where they
//   were. PIN errors (`pin`, `locked`, `current-pin` …) stay with the form that sent the PIN.
// - A request that gets no response at all is a NetworkError (the header then says '연결 안 됨').
// - Fixture mode (DEV and the e2e build only) swaps `fetch` for one that answers from a bundle,
//   so every path below runs the same way with or without a server.
import type { ApiErrorBody, ApiErrorCode } from './types';

export class ApiError extends Error {
  readonly status: number;
  /** The contract's error code (`pin`, `locked`, `preview-changed` …) or `http-<status>`. */
  readonly code: string;
  /** The JSON body as sent, including extra fields like `remaining` or `preview`. */
  readonly body: ApiErrorBody | null;

  constructor(status: number, code: string, body: ApiErrorBody | null) {
    super(`${String(status)} ${code}`);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

/** No response: offline, DNS, server down, or the connection dropped. */
export class NetworkError extends Error {
  constructor(cause: unknown) {
    super('network', { cause });
    this.name = 'NetworkError';
  }
}

export function isApiError(error: unknown, code?: ApiErrorCode): error is ApiError {
  return error instanceof ApiError && (code === undefined || error.code === code);
}

/** The contract's code for "no session" (오류 코드 표). */
const NO_SESSION: ApiErrorCode = 'session';

export type QueryValue = string | number | boolean | null | undefined;

/** /api/shell is read again every 60 s while the tab is visible (contract §읽기). */
export const SHELL_POLL_MS = 60_000;

interface ClientConfig {
  fetch: typeof fetch;
  /** Called with the path to come back to; navigates to the PIN page. */
  onAuthRequired: (next: string) => void;
  /** Fixture bundles may shorten it to play scripted sequences quickly. */
  shellPollMs: number;
}

const defaults: ClientConfig = {
  fetch: (input, init) => globalThis.fetch(input, init),
  onAuthRequired: (next) => {
    window.location.assign(pinPath(next));
  },
  shellPollMs: SHELL_POLL_MS,
};

const config: ClientConfig = { ...defaults };

/** Replace the transport, the auth redirect or the poll interval (router, fixtures, tests). */
export function configureClient(next: Partial<ClientConfig>): void {
  Object.assign(config, next);
}

/** Back to the defaults (tests). */
export function resetClient(): void {
  Object.assign(config, defaults);
}

export function shellPollMs(): number {
  return config.shellPollMs;
}

export function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null) params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

// ── return path ──────────────────────────────────────────────────────────────

/** `/pin?next=<encoded>`; the PIN page sends the user back there after entry. */
export function pinPath(next: string): string {
  const safe = safeNext(next);
  return safe ? `/pin?next=${encodeURIComponent(safe)}` : '/pin';
}

/**
 * A same-origin path to return to after PIN entry, or null. Rejects absolute and
 * protocol-relative URLs (open redirect) and the PIN page itself.
 */
export function safeNext(next: string | null | undefined): string | null {
  if (!next?.startsWith('/') || next.startsWith('//') || next.startsWith('/\\')) return null;
  if (next === '/pin' || next.startsWith('/pin?') || next.startsWith('/pin/')) return null;
  return next;
}

function currentPath(): string {
  return `${window.location.pathname}${window.location.search}${window.location.hash}`;
}

// ── requests ─────────────────────────────────────────────────────────────────

export interface RequestOptions {
  query?: Record<string, QueryValue> | undefined;
  body?: unknown;
  signal?: AbortSignal | undefined;
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as { error?: unknown }).error === 'string'
  );
}

export async function request<T>(
  method: 'GET' | 'POST' | 'PUT',
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { query, body, signal } = options;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  let res: Response;
  try {
    res = await config.fetch(buildUrl(path, query), {
      method,
      credentials: 'same-origin',
      headers,
      body: body === undefined ? null : JSON.stringify(body),
      signal: signal ?? null,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new NetworkError(error);
  }

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      throw new ApiError(res.status, res.ok ? 'bad-json' : `http-${String(res.status)}`, null);
    }
  }

  if (!res.ok) {
    const errorBody = isErrorBody(data) ? data : null;
    const code = errorBody?.error ?? `http-${String(res.status)}`;
    if (res.status === 403 && code === NO_SESSION) config.onAuthRequired(currentPath());
    throw new ApiError(res.status, code, errorBody);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, query?: Record<string, QueryValue>, signal?: AbortSignal) =>
    request<T>('GET', path, { query, signal }),
  post: <T = undefined>(path: string, body?: unknown) => request<T>('POST', path, { body }),
  put: <T = undefined>(path: string, body?: unknown) => request<T>('PUT', path, { body }),
};
