// Words of the 계획 screens and the 자산 card (pure helpers), against 기획 §5 문구 예.
import { describe, expect, it } from 'vitest';
import type { NextAction, Order, RuleCard, ScheduleItem } from '../../src/api/types';
import {
  PAPER_BUY_1007,
  PAPER_BUY_1007_FAILED,
  PAPER_FX_1007,
  PAPER_SELL_1007,
  LIVE_BUY_1007_REJECTED,
} from '../../src/fixtures/parts/common';
import {
  HOLIDAY_COMPOSITION,
  PAPER_COMPOSITION,
  homePaper,
  homeEmpty,
  homeLiveFirst,
} from '../../src/fixtures/parts/home';
import { planPaper, planStale, planWithdraw } from '../../src/fixtures/parts/plan';
import { kst } from '../../src/fixtures/world';
import { detailText, viewGroups } from '../../src/screens/Home/CompositionCard';
import { heroLabel, pnlText } from '../../src/screens/Home/Hero';
import {
  basisLineText,
  nextActionText,
  orderText,
  orderTime,
  scheduleItemText,
  stageFailure,
  stageFill,
  toneMap,
  whenText,
} from '../../src/screens/Plan/words';
import { nowTitle } from '../../src/screens/Plan/Schedule';
import { must } from './home-plan.routes';

const NOW = kst('2026-10-07', '16:10');

describe('next action', () => {
  it.each([
    [
      {
        kind: 'order',
        at: kst('2026-10-07', '22:30'),
        market: 'US',
        side: 'buy',
        instrumentName: 'S&P 500 ETF',
        qty: 2,
      },
      '오늘 22:30 미국 매수 2주',
    ],
    [
      {
        kind: 'order',
        at: kst('2026-10-08', '22:30'),
        market: 'US',
        side: 'buy',
        instrumentName: 'S&P 500 ETF',
        qty: 2,
      },
      '10/8 22:30 미국 매수 2주',
    ],
    [
      { kind: 'first-check', at: kst('2026-07-01', '08:30') },
      '첫 확인 7/1(수) 08:30 · 목표대로 매수',
    ],
    [
      { kind: 'retry', at: kst('2026-10-08', '22:30'), market: 'US', side: 'buy' },
      '10/8 22:30 미국 매수 다시 시도',
    ],
    [{ kind: 'todo', market: 'US', side: 'buy' }, '직접 할 일 · 토스 앱에서 주문 확인'],
    [
      { kind: 'holiday', markets: ['KR'], nextCheckAt: kst('2026-10-12', '08:30') },
      '한국 휴장 · 거래 없음',
    ],
    [
      { kind: 'holiday', markets: ['KR', 'US'], nextCheckAt: kst('2026-10-12', '08:30') },
      '한국·미국 휴장 · 거래 없음',
    ],
    [
      { kind: 'quote-wait', market: 'US', basisDate: '2026-10-02' },
      '미국 시세 10/2 기준 · 주문 0건',
    ],
    [{ kind: 'quote-wait', market: 'FX', basisDate: '2026-10-02' }, '환율 10/2 기준 · 주문 0건'],
    [{ kind: 'next-check', at: kst('2026-10-08', '08:30') }, '다음 확인 10/8 08:30'],
  ] as [NextAction, string][])('%o → %s', (next, text) => {
    expect(nextActionText(next, { now: NOW })).toBe(text);
  });

  it('first order: the hero line names the orders, the card only the time', () => {
    const next = {
      kind: 'first-order',
      at: kst('2026-09-01', '09:05'),
      market: 'KR',
      side: 'buy',
      count: 2,
    } as const;
    const now = kst('2026-09-01', '08:40');
    expect(nextActionText(next, { now })).toBe('오늘 09:05 첫 주문 · 한국 매수 2건');
    expect(nextActionText(next, { now, variant: 'card' })).toBe('오늘 09:05 첫 주문');
  });

  it('계획 adds 다음 확인 to 휴장', () => {
    expect(
      nextActionText(
        { kind: 'holiday', markets: ['KR'], nextCheckAt: kst('2026-10-12', '08:30') },
        { now: NOW, withNextCheck: true },
      ),
    ).toBe('한국 휴장 · 거래 없음 · 다음 확인 10/12 08:30');
  });

  it('first check: the card leaves out the weekday', () => {
    expect(
      nextActionText(
        { kind: 'first-check', at: kst('2026-07-01', '08:30') },
        { now: NOW, variant: 'card' },
      ),
    ).toBe('첫 확인 7/1 08:30 · 목표대로 매수');
  });

  it('오늘 only on the same KST day', () => {
    expect(whenText(kst('2026-10-07', '22:30'), NOW)).toBe('오늘 22:30');
    expect(whenText(kst('2026-10-08', '00:10'), NOW)).toBe('10/8 00:10');
  });
});

describe('orders and stages (값표 §1.4 · §2.2 10/7)', () => {
  it.each([
    [PAPER_SELL_1007, 'KOSPI200 ETF 매도 5주 · 181,900원', '09:05'],
    [PAPER_FX_1007, '173,000원 → $125.30 · 1,380.6원', '09:10'],
    [PAPER_BUY_1007, 'S&P 500 ETF 매수 2주 · 약 $124.80', '22:30'],
    [PAPER_BUY_1007_FAILED, 'S&P 500 ETF 매수 2주 · 시세 응답 없음', '10/7 22:30'],
    [LIVE_BUY_1007_REJECTED, 'S&P 500 ETF 매수 2주 · 토스 주문 거부', '10/7 22:30'],
  ] as [Order, string, string][])('%#: %s', (order, text, time) => {
    expect(orderText(order)).toBe(text);
    expect(orderTime(order)).toBe(time);
  });

  it('a filled stage is labeled 모의/실제 체결; a pending one is not', () => {
    const stages = planPaper().schedule.now?.stages ?? [];
    expect(stages.map((s) => stageFill(s))).toEqual(['모의 체결', '모의 체결', null]);
  });

  it('a failed stage retries at its time or becomes 직접 할 일', () => {
    expect(
      stageFailure({
        kind: 'buy',
        status: 'failed',
        at: kst('2026-10-07', '22:30'),
        orders: [PAPER_BUY_1007_FAILED],
      }),
    ).toEqual({
      retryAt: kst('2026-10-08', '22:30'),
      manual: false,
    });
    expect(
      stageFailure({
        kind: 'buy',
        status: 'failed',
        at: kst('2026-10-07', '22:30'),
        orders: [LIVE_BUY_1007_REJECTED],
      })?.manual,
    ).toBe(true);
  });

  it("'지금' titles", () => {
    expect(nowTitle({ ruleId: 'index_half', status: 'in-progress', stages: [] }, false)).toBe(
      '지금 · 리밸런싱 중 · 주문 0건',
    );
    expect(nowTitle({ ruleId: 'index_half', status: 'quote-wait', stages: [] }, false)).toBe(
      '지금 · 시세 대기 · 주문 0건',
    );
  });
});

describe('schedule items', () => {
  it.each([
    [{ kind: 'next-check', at: kst('2026-10-08', '08:30') }, '10/8 08:30', '다음 확인', null],
    [
      { kind: 'holiday', date: '2026-10-09', markets: ['KR'] },
      '10/9',
      '한국 휴장 · 거래 없음',
      null,
    ],
    [
      { kind: 'retry', at: kst('2026-10-08', '22:30'), market: 'US', side: 'buy' },
      '10/8 22:30',
      '미국 매수 다시 시도',
      null,
    ],
    [{ kind: 'sub-share-cash', krw: 56_548 }, '원화 현금', '1주 미만 대기', '56,548원'],
    [{ kind: 'new-cash', krw: 300_000 }, null, '새 현금 300,000원 · 다음 확인에 목표대로', null],
    [
      { kind: 'first-check', at: kst('2026-07-01', '08:30') },
      null,
      '첫 확인 7/1 08:30 · 목표대로 매수',
      null,
    ],
  ] as [ScheduleItem, string | null, string, string | null][])(
    '%o',
    (item, caption, title, chip) => {
      const t = scheduleItemText(item);
      expect([t.caption, t.title, t.chip]).toEqual([caption, title, chip]);
    },
  );
});

describe('basis lines', () => {
  const [index, momentum] = planPaper().rules as [RuleCard, RuleCard];
  it.each([
    [index, '규칙 안 비중 · 원화 기준 · 매수 대기 달러 포함 · 환율 1,382.4원 16:00'],
    [momentum, '규칙 안 비중 · 원화 기준 · 환율 1,382.4원 16:00'],
    [must(planStale().rules[0]), '규칙 안 비중 · 미국 시세 10/2 기준이라 계산 안 함'],
    [
      must(planWithdraw().rules[0]),
      '규칙 안 비중 · 원화 기준 · 출금 대기 현금 제외 · 환율 1,382.4원 16:00',
    ],
  ])('%#', (card, text) => {
    expect(basisLineText(card)).toBe(text);
  });
});

describe('자산 words', () => {
  it('hero labels', () => {
    expect(heroLabel(homePaper())).toBe('모의투자 자산 · 7/1부터');
    expect(heroLabel(homeLiveFirst())).toBe('실전 자산 · 9/1 시작');
    expect(heroLabel(homeEmpty())).toBe('모의투자 시작 금액');
  });

  it('PnL chip: arrow, signed won and two-decimal %; the % hides when its base is 0', () => {
    expect(pnlText({ amount: 243_800, pct: 2.44 })).toBe('▲ +243,800원 · +2.44%');
    expect(pnlText({ amount: -47_400, pct: -0.47 })).toBe('▼ −47,400원 · −0.47%');
    expect(pnlText({ amount: 12_000, pct: null })).toBe('▲ +12,000원');
  });

  it('row second lines: shares, coins (1억 단위) and dollars', () => {
    const rows = PAPER_COMPOSITION.groups.flatMap((g) => g.rows);
    expect(rows.map((r) => detailText(r))).toEqual([
      '115주 · 평균 32,005원',
      '46주 · 평균 $65.94',
      null,
      '14주 · 평균 55,508원',
      '3주 · 평균 $172.17',
      '0.0027 BTC · 평균 1억 5,493만원',
      null,
    ]);
  });

  it('통화 and 종목 groupings keep the % sums', () => {
    const tones = toneMap([]);
    const byCurrency = viewGroups(HOLIDAY_COMPOSITION, 'currency', tones);
    expect(byCurrency.map((g) => [g.name, g.pct])).toEqual([
      ['원화', 52.5],
      ['달러', 47.5],
    ]);
    const byInstrument = viewGroups(PAPER_COMPOSITION, 'instrument', tones);
    expect(byInstrument.map((g) => g.pct)).toEqual([40.7, 38.7, 7.7, 7.1, 3.5, 2.3]);
  });
});
