// Fixture runtime and the invariants every bundle must keep (예시 값표 arithmetic). The
// invariant checks run over every bundle in src/fixtures/bundles/, including future ones.
import { describe, expect, it } from 'vitest';
import type { Breakdown, HomeResponse, ShellResponse } from '../../src/api/types';
import { bundleIds, loadBundle } from '../../src/fixtures/registry';
import { fixtureFetch } from '../../src/fixtures/runtime';
import type { FixtureBundle } from '../../src/fixtures/types';

const shell: ShellResponse = {
  now: '2026-10-07T16:10:00+09:00',
  mode: 'paper',
  modeChangedAt: null,
  liveSince: null,
  status: { kind: 'ok', lastCheckAt: '2026-10-07T08:30:00+09:00' },
  banner: null,
};

const scripted: FixtureBundle = {
  id: 'home.offline',
  now: shell.now,
  responses: {
    '/api/shell': [shell, { $network: 'down' }],
    '/api/rules': { $status: 403, $body: { error: 'session' } },
    'POST /api/auth/pin': { $noContent: true },
  },
};

describe('fixture runtime', () => {
  it('lists the bundles by state id', () => {
    expect(bundleIds()).toEqual(expect.arrayContaining(['home.first-day', 'home.paper']));
  });

  it('loads a bundle and rejects unknown ids', async () => {
    expect((await loadBundle('home.paper'))?.id).toBe('home.paper');
    expect(await loadBundle('home.nope')).toBeNull();
  });

  it('answers query variants from the bare path and plays sequences', async () => {
    const fetch = fixtureFetch(scripted);
    const first = await fetch('/api/shell?ledger=paper');
    expect(first.status).toBe(200);
    expect(await first.json()).toEqual(shell);
    await expect(fetch('/api/shell')).rejects.toBeInstanceOf(TypeError);
    await expect(fetch('/api/shell')).rejects.toBeInstanceOf(TypeError); // last step repeats
  });

  it('plays HTTP failures, 204s, and 404s for anything not scripted', async () => {
    const fetch = fixtureFetch(scripted);
    const denied = await fetch('/api/rules');
    expect(denied.status).toBe(403);
    expect(await denied.json()).toEqual({ error: 'session' });
    expect((await fetch('/api/auth/pin', { method: 'POST', body: '{}' })).status).toBe(204);
    const missing = await fetch('/api/plan');
    expect(missing.status).toBe(404);
    expect(await missing.json()).toMatchObject({ error: 'not-in-fixture' });
    expect((await fetch('/api/auth/logout', { method: 'POST' })).status).toBe(404);
  });
});

/** The first answer of a script, or null when it is a failure step or missing. */
function firstStep(script: unknown): object | null {
  const step: unknown = Array.isArray(script) ? script[0] : script;
  if (typeof step !== 'object' || step === null) return null;
  if ('$status' in step || '$network' in step || '$noContent' in step) return null;
  return step;
}

const round1 = (n: number) => Math.round(n * 10) / 10;

describe.each(bundleIds())('bundle %s', (id) => {
  it('keeps the shell on the bundle clock', async () => {
    const bundle = await loadBundle(id);
    expect(bundle?.id).toBe(id);
    const s = firstStep(bundle?.responses['/api/shell']) as ShellResponse | null;
    if (s) expect(s.now).toBe(bundle?.now);
  });

  it('adds up like the 예시 값표 (rows = total, rows % = group %, groups = 100%)', async () => {
    const bundle = await loadBundle(id);
    const home = firstStep(bundle?.responses['/api/home']) as HomeResponse | null;
    if (!home) return;
    const rows = home.composition.groups.flatMap((g) => g.rows);
    expect(rows.reduce((sum, r) => sum + r.krw, 0)).toBe(home.total);
    for (const group of home.composition.groups) {
      expect(round1(group.rows.reduce((sum, r) => sum + r.pct, 0))).toBe(group.pct);
    }
    expect(round1(home.composition.groups.reduce((sum, g) => sum + g.pct, 0))).toBe(100);
    const last = home.trend.series.at(-1);
    if (last) expect(last.value).toBe(home.total);
  });

  it('balances the change breakdown (sum = end − start)', async () => {
    const bundle = await loadBundle(id);
    const b = firstStep(bundle?.responses['/api/home/breakdown']) as Breakdown | null;
    if (!b) return;
    expect(b.deposit + b.withdrawal + b.market + b.dividend + b.fees).toBe(b.end - b.start);
  });
});
