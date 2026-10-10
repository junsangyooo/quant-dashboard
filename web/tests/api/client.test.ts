import { describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  NetworkError,
  api,
  buildUrl,
  configureClient,
  isApiError,
  pinPath,
  safeNext,
} from '../../src/api/client';

function respond(status: number, body?: unknown) {
  return vi.fn<typeof fetch>(() =>
    Promise.resolve(
      new Response(body === undefined ? null : JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  );
}

describe('api client', () => {
  it('sends same-origin JSON requests and drops empty query values', async () => {
    const fetch = respond(200, { ok: true });
    configureClient({ fetch });
    await api.get('/api/home', { ledger: 'paper', period: undefined, year: null });
    const [url, init] = fetch.mock.calls[0] ?? [];
    expect(url).toBe('/api/home?ledger=paper');
    expect(init?.credentials).toBe('same-origin');
    expect(init?.method).toBe('GET');
    expect(new Headers(init?.headers).get('Accept')).toBe('application/json');
  });

  it('posts JSON bodies and treats 204 as no content', async () => {
    const fetch = respond(204);
    configureClient({ fetch });
    await expect(api.post('/api/auth/pin', { pin: '123456' })).resolves.toBeUndefined();
    const init = fetch.mock.calls[0]?.[1];
    expect(init?.body).toBe('{"pin":"123456"}');
    expect(new Headers(init?.headers).get('Content-Type')).toBe('application/json');
  });

  it('turns error JSON into ApiError with the contract code and body', async () => {
    configureClient({ fetch: respond(409, { error: 'preview-changed', preview: null }) });
    const error = await api.post('/api/mode/live', {}).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(isApiError(error, 'preview-changed')).toBe(true);
    expect((error as ApiError).status).toBe(409);
    expect((error as ApiError).body).toEqual({ error: 'preview-changed', preview: null });
  });

  it('names non-JSON errors by status', async () => {
    configureClient({
      fetch: vi.fn<typeof fetch>(() => Promise.resolve(new Response('<html>', { status: 502 }))),
    });
    await expect(api.get('/api/shell')).rejects.toMatchObject({ code: 'http-502' });
  });

  it('raises NetworkError when there is no response', async () => {
    configureClient({
      fetch: vi.fn<typeof fetch>(() => Promise.reject(new TypeError('Failed to fetch'))),
    });
    await expect(api.get('/api/shell')).rejects.toBeInstanceOf(NetworkError);
  });

  it('sends the user to /pin on a session 403 and remembers the page', async () => {
    const onAuthRequired = vi.fn();
    window.history.pushState({}, '', '/day/2026-08-21?ledger=paper');
    configureClient({ fetch: respond(403, { error: 'session' }), onAuthRequired });
    await expect(api.get('/api/day/2026-08-21')).rejects.toMatchObject({
      status: 403,
      code: 'session',
    });
    expect(onAuthRequired).toHaveBeenCalledWith('/day/2026-08-21?ledger=paper');
    window.history.pushState({}, '', '/');
  });

  it('leaves PIN errors to the form that sent the PIN', async () => {
    const onAuthRequired = vi.fn();
    configureClient({ fetch: respond(403, { error: 'pin', remaining: 2 }), onAuthRequired });
    const error = await api.post('/api/auth/pin', { pin: '000000' }).catch((e: unknown) => e);
    expect(isApiError(error, 'pin')).toBe(true);
    expect((error as ApiError).body).toMatchObject({ remaining: 2 });

    const until = '2026-10-07T16:40:00+09:00';
    configureClient({ fetch: respond(403, { error: 'locked', until, scope: 'ip' }) });
    const locked = await api
      .post('/api/account/pin', { current: '000000', next: '123456' })
      .catch((e: unknown) => e);
    expect(isApiError(locked, 'locked')).toBe(true);
    expect((locked as ApiError).body).toMatchObject({ until, scope: 'ip' });
    expect(onAuthRequired).not.toHaveBeenCalled();
  });
});

describe('return path', () => {
  it('keeps same-origin paths and refuses the rest', () => {
    expect(safeNext('/day/2026-08-21?ledger=paper')).toBe('/day/2026-08-21?ledger=paper');
    expect(safeNext('//evil.example')).toBeNull();
    expect(safeNext('/\\evil.example')).toBeNull();
    expect(safeNext('https://evil.example')).toBeNull();
    expect(safeNext('/pin?next=/')).toBeNull();
    expect(safeNext(null)).toBeNull();
  });

  it('reads next as the browser would: control characters cannot hide another site', () => {
    // next=%2F%09%2Fevil.example — the URL parser drops the tab: '//evil.example'.
    expect(safeNext(decodeURIComponent('%2F%09%2Fevil.example'))).toBeNull();
    expect(safeNext('/\n/evil.example')).toBeNull();
    expect(safeNext('/\r\n/evil.example/x')).toBeNull();
    expect(safeNext('\t//evil.example')).toBeNull();
    expect(safeNext('/\\/evil.example')).toBeNull();
    expect(safeNext('javascript:alert(1)')).toBeNull();
    expect(safeNext('data:text/html,x')).toBeNull();
    expect(safeNext(`${window.location.origin}.evil.example/`)).toBeNull();
    expect(safeNext('')).toBeNull();
    // Same-origin results come back as path, query and hash only.
    expect(safeNext(`${window.location.origin}/health#todo`)).toBe('/health#todo');
    expect(safeNext('/day/../plan?drift=1y')).toBe('/plan?drift=1y');
    expect(safeNext('/\t/health')).toBeNull(); // '//health' is a host named health
    expect(safeNext('/ho\tme')).toBe('/home');
    expect(safeNext('/pin/x')).toBeNull();
    expect(safeNext('/pinboard')).toBe('/pinboard');
  });

  it('builds the PIN link', () => {
    expect(pinPath('/day/2026-08-21?ledger=paper')).toBe(
      '/pin?next=%2Fday%2F2026-08-21%3Fledger%3Dpaper',
    );
    expect(pinPath('//evil')).toBe('/pin');
    expect(buildUrl('/api/plan', { drift: '1y' })).toBe('/api/plan?drift=1y');
  });
});
