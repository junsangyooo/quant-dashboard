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

  it('asks for the password again on 403 need_confirm and resends once with the token', async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ error: 'x', need_confirm: true, action: 'toss_key_delete', title: 't' }),
          { status: 403 },
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    const onConfirmRequired = vi.fn(() => Promise.resolve('one-time'));
    configureClient({ fetch, onConfirmRequired });
    await expect(api.delete('/api/connect/toss')).resolves.toEqual({ ok: true });
    expect(onConfirmRequired).toHaveBeenCalledWith({ action: 'toss_key_delete', title: 't' });
    const init = (fetch.mock.calls[1] as unknown as [string, RequestInit])[1];
    expect((init.headers as Record<string, string>)['X-Confirm-Token']).toBe('one-time');
  });

  it('a cancelled password ask keeps the 403', async () => {
    configureClient({
      fetch: answer(403, { error: 'x', need_confirm: true, action: 'a' }),
      onConfirmRequired: () => Promise.resolve(null),
    });
    const e = (await api.delete('/api/connect/toss').catch((x: unknown) => x)) as ApiError;
    expect(e.status).toBe(403);
  });
});
