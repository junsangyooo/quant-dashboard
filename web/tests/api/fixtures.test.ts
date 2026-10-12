// Fixture runtime and the invariants every bundle must keep (예시 값표 arithmetic). The
// invariant checks run over every bundle in src/fixtures/bundles/, including future ones.
import { describe, expect, it } from 'vitest';
import type { Breakdown, CompRow, HomeResponse, ShellResponse } from '../../src/api/types';
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
  let step: unknown = Array.isArray(script) ? script[0] : script;
  // Before any write, an { $afterWrite } step answers its $before.
  while (typeof step === 'object' && step !== null && '$afterWrite' in step && '$before' in step) {
    step = step.$before;
  }
  // A delayed answer counts as its payload; a pending one has none.
  if (typeof step === 'object' && step !== null && '$delayMs' in step && '$then' in step) {
    step = step.$then;
  }
  if (typeof step !== 'object' || step === null) return null;
  if ('$status' in step || '$network' in step || '$noContent' in step || '$pending' in step) {
    return null;
  }
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

  it('splits into its accounts like the engine (accounts add up, each in its own money)', async () => {
    const bundle = await loadBundle(id);
    const responses = bundle?.responses as Record<string, unknown> | undefined;
    const homes = Object.entries(responses ?? {})
      .filter(([key]) => key === '/api/home' || key.startsWith('/api/home?'))
      .map(([, script]) => firstStep(script) as HomeResponse | null);
    for (const home of homes) if (home?.accounts) checkAccounts(home);
  });

  function checkAccounts(home: HomeResponse) {
    if (!home.accounts) return;
    // 전체 손익 = 한국 + 미국 in won + 환율 효과, to the won.
    const { kr, us, fx } = home.accounts.split;
    expect(kr + us + fx).toBe(home.pnl?.amount);
    expect(home.accounts.list.map((a) => [a.id, a.currency])).toEqual([
      ['kr', 'KRW'],
      ['us', 'USD'],
    ]);
    for (const account of home.accounts.list) {
      const dollars = account.currency === 'USD';
      const amount = (r: CompRow) => (dollars ? cents(r.usd ?? Number.NaN) : r.krw);
      const rows = account.composition.groups.flatMap((g) => g.rows);
      expect(rows.reduce((s, r) => s + amount(r), 0)).toBe(
        dollars ? cents(account.total) : account.total,
      );
      for (const group of account.composition.groups) {
        expect(round1(group.rows.reduce((s, r) => s + r.pct, 0))).toBe(group.pct);
        expect(group.target).toBeNull();
      }
      if (rows.length > 0) {
        expect(round1(account.composition.groups.reduce((s, g) => s + g.pct, 0))).toBe(100);
      }
      const last = account.trend.series.at(-1);
      if (last) expect(last.value).toBe(account.total);
      for (const p of account.trend.series)
        expect([p.baseline, p.baselineRet]).toEqual([null, null]);
      if (account.id === 'kr' && account.pnl) expect(account.pnl.amount).toBe(kr);
      if (account.pnl === null) expect(account.total).toBe(0);
      // The period chips follow the account's own record; the period P&L only with chips.
      if (account.trend.periods === null) expect(account.trend.periodPnl).toBeNull();
    }
  }

  it('balances every account breakdown in its own money (transfers included)', async () => {
    const bundle = await loadBundle(id);
    const responses = bundle?.responses as Record<string, unknown> | undefined;
    for (const [key, script] of Object.entries(responses ?? {})) {
      if (!key.startsWith('/api/home/breakdown?') || !key.includes('account=')) continue;
      const b = firstStep(script) as Breakdown | null;
      if (!b) continue;
      const parts = [b.deposit, b.withdrawal, b.transfer ?? 0, b.market, b.dividend, b.fees];
      expect(
        parts.reduce((s, v) => s + cents(v), 0),
        key,
      ).toBe(cents(b.end) - cents(b.start));
      expect(b.currency, key).toBe(key.includes('account=us') ? 'USD' : 'KRW');
    }
  });
});

/** Dollars as whole cents (sums of dollar figures without float dust). */
function cents(usd: number): number {
  return Math.round(usd * 100);
}
