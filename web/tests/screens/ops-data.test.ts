// The 작동 · 모의투자·실전 · 설정 · 입장 bundles hold the 예시-값표 numbers, and the text builders
// turn them into the drawn words.
import { describe, expect, it } from 'vitest';
import type {
  HealthResponse,
  HistoryResponse,
  ModeResponse,
  ShellResponse,
} from '../../src/api/types';
import { bundleIds, loadBundle } from '../../src/fixtures/registry';
import { fixtureFetch } from '../../src/fixtures/runtime';
import {
  LIVE_OFF_PREVIEW,
  PERFORMANCE,
  PERFORMANCE_SHORT,
  PREVIEW_OK,
  TWO_LEDGERS,
  modeLive,
  modePaper,
  shell,
} from '../../src/fixtures/ops';
import type { FixtureBundle } from '../../src/fixtures/types';
import {
  ageFill,
  atTime,
  checkCount,
  recentWeeks,
  runLine,
  sourceView,
  summaryView,
  todoView,
} from '../../src/screens/Health/text';
import {
  blockedLine,
  blockingCauses,
  cashStaysLine,
  stageView,
  topicParticle,
  usdWhole,
  withSubject,
} from '../../src/screens/Mode/text';
import { retAxis } from '../../src/screens/Mode/TwoLedgers';
import { deviceLabel } from '../../src/screens/Account/Devices';

const MINE = /^(health|mode|account|pin)\./;

/** The first answer of a script before any write. */
function first(script: unknown): unknown {
  let step: unknown = Array.isArray(script) ? script[0] : script;
  while (typeof step === 'object' && step !== null && '$afterWrite' in step && '$before' in step) {
    step = step.$before;
  }
  return step;
}

describe('예시-값표 numbers in the bundles', () => {
  it('has a bundle for every drawn frame and the spec-only states', () => {
    const ids = bundleIds().filter((id) => MINE.test(id));
    expect(ids).toEqual(
      expect.arrayContaining([
        'health.todo',
        'health.stale',
        'health.unknown',
        'health.failed',
        'health.empty',
        'health.loading',
        'health.permission',
        'health.phase2',
        'mode.paper',
        'mode.live',
        'mode.turning-on',
        'mode.off-confirm',
        'mode.off-failed',
        'mode.blocked',
        'mode.short',
        'mode.empty',
        'mode.loading',
        'mode.live-stale',
        'mode.live-not-available',
        'mode.preview-changed',
        'mode.permission',
        'account.default',
        'account.no-push',
        'account.empty',
        'account.loading',
        'account.error',
        'account.pin-error',
        'account.push-not-ready',
        'account.permission',
        'pin.entering',
        'pin.error',
        'pin.locked',
        'pin.global-lock',
        'pin.no-pin',
        'pin.loading',
      ]),
    );
  });

  it('keeps 성적 at 71 · 3 · 1 · 13, +2.44% · +243,800원, 기준선 +3.59% (and 12 · 0 · 0 · 6 short)', () => {
    expect(PERFORMANCE).toMatchObject({ checks: 71, rebalances: 3, failures: 1, paperFills: 13 });
    expect(PERFORMANCE.ret).toEqual({ pct: 2.44, amount: 243_800 });
    expect(PERFORMANCE.baselinePct).toBe(3.59);
    expect(PERFORMANCE_SHORT).toMatchObject({
      checks: 12,
      rebalances: 0,
      failures: 0,
      paperFills: 6,
      ret: null,
    });
  });

  it('keeps the 성적 tiles equal to the 기록 summary tiles (확인 71 · 리밸런싱 3 · 실패 1)', async () => {
    const bundle = await loadBundle('history.paper');
    const history = first(bundle?.responses['/api/history']) as HistoryResponse;
    expect(PERFORMANCE.checks).toBe(history.tiles.checks.count);
    expect(PERFORMANCE.failures).toBe(history.tiles.checks.failed);
    expect(PERFORMANCE.rebalances).toBe(history.tiles.rebalances.count);
  });

  it('keeps the preview at 10,000,000원 → 환전 약 4,705,000원 → $3,403 · 매수 4,775,700원 · $3,399.60', () => {
    expect(PREVIEW_OK.current).toEqual([{ label: 'krw-cash', krw: 10_000_000 }]);
    const [fx, buy] = PREVIEW_OK.stages;
    expect(fx?.orders[0]?.fx).toEqual({ krw: 4_705_000, usd: 3403, rate: 1382.4 });
    const krw = (buy?.orders ?? []).reduce((s, o) => s + (o.amountKrw ?? 0), 0);
    const usd = (buy?.orders ?? []).reduce((s, o) => s + (o.amountUsd ?? 0), 0);
    expect(krw).toBe(4_775_700);
    expect(Math.round(usd * 100) / 100).toBe(3399.6);
    // The 환전 covers the US buys plus their 0.1% fee.
    expect(Math.round(usd * 1.001)).toBe(3403);
    expect(PREVIEW_OK.outside).toEqual([
      expect.objectContaining({ qty: 0.0027, approxKrw: 355_000 }),
    ]);
    // Targets: 지수 반반 80% (40 · 40), 모멘텀 20% (42 · 40 · 18 of it).
    expect(PREVIEW_OK.target.map((t) => t.pct)).toEqual([40, 40, 8.4, 8, 3.6]);
    expect(Math.round(PREVIEW_OK.target.reduce((s, t) => s + t.pct, 0) * 10) / 10).toBe(100);
  });

  it('ends the two ledgers on +1.13% · +1.28% · +1.75% with a −0.15%p breakdown', () => {
    const last = TWO_LEDGERS.series.at(-1);
    expect(last).toMatchObject({ live: 10_112_670, paper: 10_243_800, baseline: 10_175_000 });
    expect(last).toMatchObject({ liveRet: 1.13, paperRet: 1.28, baselineRet: 1.75 });
    expect(TWO_LEDGERS.endRet).toEqual({ live: 1.13, paper: 1.28, baseline: 1.75 });
    const b = TWO_LEDGERS.breakdown;
    expect(Math.round((b.fills + b.fees + b.other) * 100) / 100).toBe(b.total);
    expect(Math.round((TWO_LEDGERS.endRet.live - TWO_LEDGERS.endRet.paper) * 100) / 100).toBe(
      b.total,
    );
    expect(TWO_LEDGERS.series).toHaveLength(27); // 실전 9/1~10/7 = 27일째
  });

  // The off modal used to read the live ledger's /api/home and /api/plan; the contract now sends
  // what turning off does in /api/mode offPreview, so the check moved there (same §2.2 numbers).
  it('turning live off cancels the pending buy and leaves 달러 현금 $125.67 (offPreview)', () => {
    expect(modeLive().offPreview).toBe(LIVE_OFF_PREVIEW);
    expect(modePaper().offPreview).toBeNull();
    expect(LIVE_OFF_PREVIEW.cancel).toEqual([
      expect.objectContaining({ status: 'pending', qty: 2, amountUsd: 124.8 }),
    ]);
    const usd = LIVE_OFF_PREVIEW.cash.find((c) => c.currency === 'USD');
    expect(usd).toEqual({ currency: 'USD', usd: 125.67, krw: 173_726 });
    expect(LIVE_OFF_PREVIEW.cash.find((c) => c.currency === 'KRW')?.krw).toBe(85_964);
  });

  it.each(bundleIds().filter((id) => MINE.test(id)))(
    '%s: shell on the bundle clock, totals match',
    async (id) => {
      const bundle = await loadBundle(id);
      if (!bundle) throw new Error(id);
      const s = first(bundle.responses['/api/shell']) as ShellResponse | null;
      if (s && 'now' in s) expect(s.now).toBe(bundle.now);
      const h = first(bundle.responses['/api/health']) as HealthResponse | null;
      if (h && 'summary' in h) expect(h.summary.sourcesTotal).toBe(h.sources.length);
      const m = first(bundle.responses['/api/mode']) as ModeResponse | null;
      if (m && 'mode' in m && m.mode === 'live') expect(m.live?.days).toBe(27);
    },
  );

  it('lists the 14 recent days as the 10 weekdays 9/24–10/7', async () => {
    const bundle = await loadBundle('health.todo');
    const h = first(bundle?.responses['/api/health']) as HealthResponse;
    expect(h.recent14.map((d) => d.date)).toEqual([
      '2026-09-24',
      '2026-09-25',
      '2026-09-28',
      '2026-09-29',
      '2026-09-30',
      '2026-10-01',
      '2026-10-02',
      '2026-10-05',
      '2026-10-06',
      '2026-10-07',
    ]);
    expect(recentWeeks(h.recent14).map((w) => w.monday)).toEqual([
      '2026-09-21',
      '2026-09-28',
      '2026-10-05',
    ]);
  });
});

describe('fixture runtime: { $afterWrite }', () => {
  it('answers $before until the write is made, then $after', async () => {
    const bundle = {
      id: 'mode.off-confirm',
      now: shell().now,
      responses: {
        '/api/shell': {
          $afterWrite: 'POST /api/mode/paper',
          $before: shell({ mode: 'live' }),
          $after: shell(),
        },
        'POST /api/mode/paper': { mode: 'paper', cancelFailed: [] },
      },
    } satisfies FixtureBundle;
    const fetch = fixtureFetch(bundle);
    const mode = async () => ((await (await fetch('/api/shell')).json()) as ShellResponse).mode;
    expect(await mode()).toBe('live');
    expect(await mode()).toBe('live');
    await fetch('/api/mode/paper', { method: 'POST' });
    expect(await mode()).toBe('paper');
  });
});

describe('작동 text', () => {
  const now = '2026-10-07T16:10:00+09:00';

  it('writes times on the same day without the date', () => {
    expect(atTime('2026-10-07T09:30:00+09:00', now)).toBe('09:30');
    expect(atTime('2026-10-08T06:20:00+09:00', now)).toBe('10/8 06:20');
  });

  it('maps the age onto two cadences', () => {
    expect(ageFill(0)).toBe(0);
    expect(ageFill(0.4)).toBe(0.2);
    expect(ageFill(1)).toBe(0.5);
    expect(ageFill(1.5)).toBe(0.75);
    expect(ageFill(5)).toBe(1);
  });

  it('writes the last-check line by result', () => {
    expect(runLine({ at: '2026-10-07T08:30:00+09:00', result: 'rebalance', seconds: 42 })).toBe(
      '10/7 08:30 확인 · 리밸런싱 시작 · 42초',
    );
    expect(
      runLine({
        at: '2026-10-07T08:30:00+09:00',
        result: 'failed',
        seconds: 12,
        reason: 'no-quote',
      }),
    ).toBe('10/7 08:30 확인 실패 · 시세 응답 없음 · 12초');
    expect(runLine({ at: '2026-10-07T08:30:00+09:00', result: 'quote-wait', seconds: 6 })).toBe(
      '10/7 08:30 확인 · 시세 대기 · 주문 0건',
    );
  });

  it('counts 점검 by cause and words the summary', async () => {
    const stale = first(
      (await loadBundle('health.stale'))?.responses['/api/health'],
    ) as HealthResponse;
    expect(checkCount(stale)).toBe(1);
    expect(summaryView(stale, now)).toMatchObject({
      label: '점검 1',
      line: '자료 6개 중 낡음 1 · 할 일 1',
    });
    const card = stale.todos[0];
    if (!card) throw new Error('todo');
    expect(todoView(card, now)).toMatchObject({
      title: '미국 시세 10/2 기준 · 2거래일째',
      chip: '10/8 06:20 자동 재시도',
      lines: ['10/5·10/6 미국 종가를 못 받았어요', '다음 시도 10/8 06:20'],
      result: '그동안 주문 0건 · 실전 켜기 막힘',
    });
    const us = stale.sources[1];
    if (!us) throw new Error('source');
    expect(sourceView(us, now)).toMatchObject({
      chip: '낡음',
      line: '10/2 종가(ET) · 10/3 06:20 받음 · 매일',
    });
  });
});

describe('모의투자·실전 text', () => {
  it('picks 은/는 and 이/가 by the last sound', () => {
    expect(topicParticle('$125.67')).toBe('은');
    expect(topicParticle('$124.80')).toBe('은');
    expect(topicParticle('$3,402')).toBe('는');
    expect(topicParticle('85,964원')).toBe('은');
    expect(withSubject('미국 시세')).toBe('미국 시세가');
    expect(withSubject('환율')).toBe('환율이');
    expect(cashStaysLine('USD', 125.67)).toBe('달러 현금 $125.67은 계좌에 남아요');
  });

  it('rounds 약 dollar sums to whole dollars', () => {
    expect(usdWhole(3399.6)).toBe('$3,400');
    expect(usdWhole(3403)).toBe('$3,403');
  });

  it('words each stage', () => {
    const [fx, buy] = PREVIEW_OK.stages;
    if (!fx || !buy) throw new Error('stages');
    const now = '2026-10-07T16:10:00+09:00';
    expect(stageView(fx, now)).toMatchObject({
      label: '환전 · 원→달러',
      time: '10/8 09:10 예상',
      body: ['약 4,705,000원'],
      amount: '→ 약 $3,403',
      note: '환율 1,382.4원',
    });
    expect(stageView(buy, now)).toMatchObject({
      label: '매수 · 4건',
      time: '한국 09:05 · 미국 22:30',
      body: ['한국 · KOSPI200 ETF 110주 · 삼성전자 14주', '미국 · S&P 500 ETF 46주 · NVDA 3주'],
      amount: '약 4,775,700원 · 약 $3,400',
    });
  });

  it('counts the blocking causes once and words the closed card', async () => {
    const blocked = first(
      (await loadBundle('mode.blocked'))?.responses['/api/mode'],
    ) as ModeResponse;
    expect(blockingCauses(blocked.preflight)).toEqual({ count: 1, names: ['미국 시세'] });
    expect(blockedLine(blocked)).toBe('점검 1개(미국 시세) 해결 뒤 켤 수 있어요');
    expect(blockedLine(modePaper())).toBeNull();
    expect(blockedLine(modePaper({ canTurnOn: { ok: false, cause: 'live-not-available' } }))).toBe(
      '토스 주문 연결 뒤 켤 수 있어요',
    );
  });

  it('draws a 0% line and one nice tick for returns', () => {
    const axis = retAxis([-0.24, 1.13, 1.28, 1.75]);
    expect(axis.ticks).toEqual([0, 1.5]);
    expect(axis.domain[0]).toBeLessThan(-0.24);
    expect(axis.domain[1]).toBeGreaterThan(1.75);
  });
});

describe('설정 text', () => {
  it('names a home-screen iPhone app like the drawing', () => {
    expect(deviceLabel({ name: 'iPhone', kind: 'iphone-app', enteredAt: '' })).toBe(
      'iPhone · 홈 화면 앱',
    );
    expect(deviceLabel({ name: 'Mac · Chrome', kind: 'mac', enteredAt: '' })).toBe('Mac · Chrome');
  });
});
