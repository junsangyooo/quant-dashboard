// Fixture mode: answers /api/* from a bundle instead of the network. Loaded only when
// `?fixture=<state id>` is present in DEV or the e2e build (see main.tsx); production builds
// cannot import this module (vite.config.ts fails the build if they do).
import { configureClient } from '../api/client';
import { loadBundle } from './registry';
import type { FixtureBundle } from './types';

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

/** A fetch that never touches the network: it plays the bundle's scripted responses. */
export function fixtureFetch(bundle: FixtureBundle): typeof fetch {
  // Keys are '/api/…' (GET, optionally with its query) or 'POST /api/…'; values are steps.
  const responses = bundle.responses as Record<string, unknown>;
  const calls = new Map<string, number>();
  // Writes made so far ('POST /api/mode/paper'), for { $afterWrite } steps.
  const writes = new Set<string>();

  return (input, init) => {
    const raw = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(raw, 'http://fixture.invalid');
    const method = (init?.method ?? 'GET').toUpperCase();
    if (method !== 'GET') writes.add(`${method} ${url.pathname}`);
    const candidates =
      method === 'GET'
        ? [`${url.pathname}${url.search}`, url.pathname]
        : [`${method} ${url.pathname}`];
    const key = candidates.find((k) => responses[k] !== undefined);
    if (key === undefined) {
      return Promise.resolve(
        json(404, {
          error: 'not-in-fixture',
          detail: { fixture: bundle.id, method, path: candidates[0] },
        }),
      );
    }
    const script = responses[key];
    const n = calls.get(key) ?? 0;
    calls.set(key, n + 1);
    // A sequence plays in call order; its last step repeats.
    let step: unknown = Array.isArray(script) ? script[Math.min(n, script.length - 1)] : script;
    // { $afterWrite, $before, $after } switches once that write has been made.
    while (isObject(step) && typeof step.$afterWrite === 'string') {
      step = writes.has(step.$afterWrite) ? step.$after : step.$before;
    }

    // { $pending: true } never answers (loading states); an abort still ends it.
    if (isObject(step) && step.$pending === true) {
      return new Promise<Response>((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => {
          reject(new DOMException('Aborted', 'AbortError'));
        });
      });
    }
    // { $delayMs, $then } answers $then after the delay (skeleton first, then the data).
    if (isObject(step) && typeof step.$delayMs === 'number') {
      const delay = step.$delayMs;
      const then = step.$then;
      return new Promise<Response>((resolve, reject) => {
        const timer = setTimeout(() => {
          resolve(json(200, then));
        }, delay);
        init?.signal?.addEventListener('abort', () => {
          clearTimeout(timer);
          reject(new DOMException('Aborted', 'AbortError'));
        });
      });
    }

    if (isObject(step) && step.$network === 'down') {
      return Promise.reject(new TypeError(`fixture ${bundle.id}: network down for ${key}`));
    }
    if (isObject(step) && typeof step.$status === 'number') {
      return Promise.resolve(json(step.$status, step.$body));
    }
    if (isObject(step) && step.$noContent === true) {
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    return Promise.resolve(json(200, step));
  };
}

let active: FixtureBundle | null = null;

/** The bundle the app is answering from, or null outside fixture mode. */
export function activeFixture(): FixtureBundle | null {
  return active;
}

/**
 * Switch the API client to a bundle. An unknown id still installs fixture mode with no
 * responses, so the screen shows its error states instead of reaching a server.
 */
export async function installFixture(id: string): Promise<FixtureBundle | null> {
  const bundle = await loadBundle(id);
  if (!bundle) console.error(`[fixture] no bundle named "${id}" in src/fixtures/bundles/`);
  const effective: FixtureBundle = bundle ?? {
    id: 'home.paper',
    now: new Date(0).toISOString(),
    responses: {},
  };
  configureClient({
    fetch: fixtureFetch(effective),
    ...(effective.shellPollMs !== undefined ? { shellPollMs: effective.shellPollMs } : {}),
  });
  active = bundle;
  return bundle;
}
