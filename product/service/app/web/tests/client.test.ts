import { describe, expect, it, vi } from 'vitest';
import { api, ApiError, configureClient, NetworkError } from '../src/api/client';

function answer(status: number, body: unknown) {
  return vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status })));
}

describe('api client', () => {
  it('sends JSON and returns the body', async () => {
    const fetch = answer(200, { ok: true });
    configureClient({ fetch });
    await expect(api.post('/api/x', { a: 1 })).resolves.toEqual({ ok: true });
    const init = (fetch.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.body).toBe('{"a":1}');
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json');
  });

  it('sends the user to 로그인 only when the session is gone', async () => {
    const onLoginRequired = vi.fn();
    configureClient({ fetch: answer(401, { error: 'x', tries_left: 3 }), onLoginRequired });
    await expect(api.post('/api/login', {})).rejects.toBeInstanceOf(ApiError);
    expect(onLoginRequired).not.toHaveBeenCalled();
    configureClient({ fetch: answer(401, { error: 'x', need_login: true }), onLoginRequired });
    await expect(api.get('/api/home')).rejects.toBeInstanceOf(ApiError);
    expect(onLoginRequired).toHaveBeenCalledOnce();
  });

  it('keeps the server message and extras', async () => {
    configureClient({ fetch: answer(429, { error: '잠금', locked_for: 120 }) });
    const e = (await api.post('/api/login', {}).catch((x: unknown) => x)) as ApiError;
    expect(e.message).toBe('잠금');
    expect(e.body?.locked_for).toBe(120);
  });

  it('a dropped connection is a NetworkError', async () => {
    configureClient({ fetch: vi.fn(() => Promise.reject(new TypeError('failed'))) });
    await expect(api.get('/api/home')).rejects.toBeInstanceOf(NetworkError);
  });
});
