// SCR-PLAN states (기획 §5 상태 표) and the remaining 완료 조건.
import { screen, waitFor, within } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';
import { configureClient, pinPath } from '../../src/api/client';
import type { Instrument, PlanResponse, RuleCard, RuleRef } from '../../src/api/types';
import { ruleStatusChip } from '../../src/api/adapters';
import planEmpty from '../../src/fixtures/bundles/plan.empty';
import planFirstDay from '../../src/fixtures/bundles/plan.first-day';
import planHoliday from '../../src/fixtures/bundles/plan.holiday';
import planLive from '../../src/fixtures/bundles/plan.live';
import planLiveTodo from '../../src/fixtures/bundles/plan.live-todo';
import planLoading from '../../src/fixtures/bundles/plan.loading';
import planOffline from '../../src/fixtures/bundles/plan.offline';
import planPaperBundle from '../../src/fixtures/bundles/plan.paper';
import planPartial from '../../src/fixtures/bundles/plan.partial';
import planPermission from '../../src/fixtures/bundles/plan.permission';
import planStale from '../../src/fixtures/bundles/plan.stale';
import planWithdraw from '../../src/fixtures/bundles/plan.withdraw';
import { planPaper } from '../../src/fixtures/parts/plan';
import type { FixtureBundle } from '../../src/fixtures/types';
import { kst } from '../../src/fixtures/world';
import { must, renderState, stubScroll, textOf } from './home-plan.routes';

beforeAll(stubScroll);

const SEVEN = [
  '목표 범위 안',
  '리밸런싱 예정',
  '리밸런싱 중',
  '일부 실패',
  '휴장',
  '시세 대기',
  '출금 대기',
];

async function openPlan(bundle: FixtureBundle) {
  renderState(bundle, '/plan');
  return screen.findAllByRole('article');
}

function nowItem() {
  return screen.getByText(/^지금 · /).closest('li') as HTMLElement;
}

describe('상태 칩 일곱 가지', () => {
  it('the rule status chips map to the seven words only', () => {
    const fixed = [
      'in-range',
      'scheduled',
      'in-progress',
      'partial-failed',
      'holiday',
      'quote-wait',
      'withdraw-wait',
    ] as const;
    expect(fixed.map((s) => ruleStatusChip(s).label)).toEqual(SEVEN);
  });

  it.each([
    planPaperBundle,
    planLive,
    planStale,
    planPartial,
    planLiveTodo,
    planFirstDay,
    planWithdraw,
    planHoliday,
    planEmpty,
  ])('$id shows only those words on its chips', async (bundle) => {
    const cards = await openPlan(bundle);
    for (const c of cards) {
      const chip = c.querySelector('[class*="rebalance"] .t-label');
      expect(SEVEN).toContain(chip?.textContent);
    }
  });
});

describe('실전 평상 (값표 §2.2)', () => {
  it("80.6% · 18.5%, '실제 체결' on filled cards, 1주 미만 대기 85,964원, drift 9/1부터 with ⏻", async () => {
    await openPlan(planLive);
    expect(textOf(screen.getByRole('article', { name: '지수 반반' }).querySelector('p'))).toBe(
      '자산의80.6%· 목표 80%',
    );
    expect(
      textOf(screen.getByRole('article', { name: '[예시] 종목 모멘텀' }).querySelector('p')),
    ).toBe('자산의18.5%· 목표 20%');
    const now = nowItem();
    expect(within(now).getAllByText('실제 체결')).toHaveLength(2);
    expect(within(now).queryByText('모의 체결')).not.toBeInTheDocument();
    expect(within(now).getByText('KOSPI200 ETF 매도 5주 · 181,850원')).toBeVisible();
    expect(within(now).getByText('173,000원 → $125.22 · 1,381.5원')).toBeVisible();
    expect(within(now).getByText('S&P 500 ETF 매수 2주 · 약 $124.80')).toBeVisible();
    expect(screen.getByText('85,964원')).toBeVisible();
    const drift = screen.getByRole('region', { name: '벗어남 흐름' });
    expect(within(drift).getByText('9/1부터')).toBeVisible();
    expect(within(drift).queryByRole('group', { name: '흐름 기간' })).not.toBeInTheDocument();
    expect(within(drift).getAllByRole('link', { name: '9/1(화) 실전 켬' })).toHaveLength(1);
  });
});

describe('일부 실패 (값표 §3, 10/8 08:40)', () => {
  it('buy card ✕ with 다시 10/8 22:30; status line and banner show the same time', async () => {
    await openPlan(planPartial);
    const index = screen.getByRole('article', { name: '지수 반반' });
    expect(within(index).getByText('일부 실패')).toBeVisible();
    expect(
      within(index).getByRole('button', { name: '10/8 22:30 미국 매수 다시 시도' }),
    ).toBeVisible();
    const now = nowItem();
    expect(within(now).getByText('지금 · 일부 실패')).toBeVisible();
    expect(within(now).getByText('다시 10/8 22:30')).toBeVisible();
    expect(within(now).getByText('S&P 500 ETF 매수 2주 · 시세 응답 없음')).toBeVisible();
    expect(within(now).getByText('10/7 22:30')).toBeVisible();
    expect(screen.getByText('10/8 22:30').closest('li')).toHaveTextContent('미국 매수 다시 시도');
    // On 계획 the banner points to 작동, not to this page (인계 불일치 10).
    const banner = screen.getByRole('status');
    expect(textOf(banner)).toBe('10/7 미국 매수 실패 · 10/8 22:30 다시 시도작동 보기');
    expect(
      within(screen.getByRole('article', { name: '[예시] 종목 모멘텀' })).getByText(
        '다음 확인 10/9 08:30',
      ),
    ).toBeVisible();
  });
});

describe('실전 일부 실패 · 직접 할 일', () => {
  it("'직접 할 일 · 토스 앱에서 주문 확인', header 직접 할 일 1, the card links to 작동", async () => {
    await openPlan(planLiveTodo);
    expect(
      screen.getByRole('button', { name: '직접 할 일 · 토스 앱에서 주문 확인' }),
    ).toBeVisible();
    expect(screen.getByRole('banner')).toHaveTextContent('직접 할 일 1');
    const now = nowItem();
    expect(within(now).getByText('지금 · 일부 실패 · 직접 할 일')).toBeVisible();
    expect(within(now).getByRole('link', { name: '직접 할 일' })).toHaveAttribute(
      'href',
      '/health',
    );
    expect(within(now).getByText('S&P 500 ETF 매수 2주 · 토스 주문 거부')).toBeVisible();
  });
});

describe('시세 대기 (값표 §3)', () => {
  it("hollow gauges without needles, weights '—', '지금 · 시세 대기 · 주문 0건', no 목표 범위 안", async () => {
    const cards = await openPlan(planStale);
    expect(cards).toHaveLength(2);
    for (const c of cards) {
      expect(c.querySelector('line.needle')).toBeNull();
      expect(c.querySelector('circle.hubEmpty')).not.toBeNull();
      expect(c.querySelector('[class*="rebalance"] .t-label')?.textContent).toBe('시세 대기');
      // Each row: '— · 목표 n%' over '시세 대기'.
      expect(within(c).getAllByText('시세 대기').length).toBeGreaterThan(2);
      expect(within(c).getByText('미국 시세 10/2 기준 · 주문 0건')).toBeVisible();
      expect(
        within(c).getByText('규칙 안 비중 · 미국 시세 10/2 기준이라 계산 안 함'),
      ).toBeVisible();
      expect(within(c).getAllByText(/^— · 목표 \d+%$/).length).toBeGreaterThan(1);
    }
    expect(screen.getAllByText('— · 목표 50%')).toHaveLength(2);
    expect(screen.getByText('지금 · 시세 대기 · 주문 0건')).toBeVisible();
    expect(screen.queryByText('목표 범위 안')).not.toBeInTheDocument();
    // The lines break from 10/5 and say so.
    expect(screen.getByText('10/5부터 시세 대기')).toBeInTheDocument();
  });
});

describe('출시 첫날 (값표 §4)', () => {
  it('no rule share bar, one card 99.6% · 목표 100%, 벗어남 흐름은 둘째 날부터', async () => {
    const cards = await openPlan(planFirstDay);
    expect(cards).toHaveLength(1);
    expect(screen.queryByRole('region', { name: '규칙별 자산 비중' })).not.toBeInTheDocument();
    expect(textOf(cards[0]?.querySelector('p') ?? null)).toBe('자산의99.6%· 목표 100%');
    expect(screen.getByText('벗어남 흐름은 둘째 날부터')).toBeVisible();
    const now = nowItem();
    expect(within(now).getByText('4,967,000원 → $3,568.24 · 1,392.0원')).toBeVisible();
    expect(within(now).getByText('KOSPI200 ETF 매수 156주 · 4,992,000원')).toBeVisible();
    expect(within(now).getByText('S&P 500 ETF 매수 54주 · 약 $3,564.00')).toBeVisible();
    expect(screen.getByText('미국 휴장 · 거래 없음')).toBeVisible();
    expect(screen.getByText('40,252원')).toBeVisible();
  });
});

describe('출금 대기 (값표 §2.3)', () => {
  it('chip 출금 대기, weights without the waiting cash (49.3 · 50.7), orders 0, no banner', async () => {
    await openPlan(planWithdraw);
    const index = screen.getByRole('article', { name: '지수 반반' });
    expect(within(index).getByText('출금 대기')).toBeVisible();
    expect(within(index).getByRole('button', { name: '10/12까지 · 리밸런싱 쉼' })).toBeVisible();
    expect(within(index).getByText('49.3% · 목표 50%')).toBeVisible();
    expect(within(index).getByText('50.7% · 목표 50%')).toBeVisible();
    expect(within(index).getByText(/출금 대기 현금 제외/)).toBeVisible();
    expect(screen.getByText('출금 대기 500,425원 · 10/12까지 · 주문 0건')).toBeVisible();
    expect(screen.getByText('출금 없으면 다음 확인에 목표대로')).toBeVisible();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});

describe('휴장 (명세, 그림 없음)', () => {
  it("chip 휴장 + '한국 휴장 · 거래 없음 · 다음 확인 10/12 08:30'", async () => {
    await openPlan(planHoliday);
    const index = screen.getByRole('article', { name: '지수 반반' });
    expect(within(index).getByText('휴장')).toBeVisible();
    expect(within(index).getByText('한국 휴장 · 거래 없음 · 다음 확인 10/12 08:30')).toBeVisible();
  });
});

describe('첫 확인 전 (명세, 그림 없음)', () => {
  it("hollow gauges, '—', '— · 목표 50%', first item 첫 확인 7/1 08:30 · 목표대로 매수", async () => {
    const cards = await openPlan(planEmpty);
    for (const c of cards) {
      expect(c.querySelector('line.needle')).toBeNull();
      expect(within(c).getByText('리밸런싱 예정')).toBeVisible();
    }
    expect(screen.getAllByText('— · 목표 50%')).toHaveLength(2);
    expect(
      screen.getByText('첫 확인 7/1 08:30 · 목표대로 매수', { selector: 'li span' }),
    ).toBeVisible();
    expect(screen.getByText('벗어남 흐름은 둘째 날부터')).toBeVisible();
  });
});

describe('로드 · 연결 끊김 · 세션 없음', () => {
  it('loading keeps card frames and gauge outlines; numbers are skeletons', async () => {
    const { container } = renderState(planLoading, '/plan');
    await waitFor(() => {
      expect(container.querySelectorAll('circle.hubEmpty').length).toBe(2);
    });
    expect(screen.getByRole('heading', { level: 2, name: '예정' })).toBeVisible();
    expect(container.textContent).not.toMatch(/\d+\.\d%/);
  });

  it("offline: header 연결 안 됨 and '16:10 불러온 값 · 연결 안 됨' on top; values stay", async () => {
    renderState({ ...planOffline, shellPollMs: 30 } satisfies FixtureBundle, '/plan');
    await screen.findByRole('article', { name: '지수 반반' });
    expect(await screen.findByText('16:10 불러온 값 · 연결 안 됨')).toBeVisible();
    expect(screen.getByRole('banner')).toHaveTextContent('연결 안 됨');
    expect(screen.getByText('50.2% · 목표 50%')).toBeVisible();
  });

  it('no session: to the PIN page and back', async () => {
    const { router } = renderState(planPermission, '/plan');
    configureClient({
      onAuthRequired: (next) => {
        void router.navigate(pinPath(next));
      },
    });
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/pin');
    });
  });
});

describe('규칙 3개 이상 · 종목 5개', () => {
  it('repeats the same card frame; the 5-instrument rule still has one needle (the most deviated)', async () => {
    const inst = (id: string, name: string, initials: string): Instrument => ({
      id,
      name,
      kind: 'stock',
      market: 'KR',
      currency: 'KRW',
      initials,
    });
    const five = [
      inst('KR:1', '가', '가'),
      inst('KR:2', '나', '나'),
      inst('KR:3', '다', '다'),
      inst('KR:4', '라', '라'),
      inst('KR:5', '마', '마'),
    ];
    const weights = [20.4, 19.1, 21.5, 19.6, 19.4];
    const rule: RuleRef = { id: 'five', name: '다섯 종목', ai: false, colorIndex: 2 };
    const fiveCard: RuleCard = {
      rule,
      share: { pct: 10.0, target: 10 },
      status: 'in-range',
      next: { kind: 'next-check', at: kst('2026-10-08', '08:30') },
      gauge: {
        kind: 'drift',
        threshold: 2,
        needle: { instrument: must(five[2]), deviation: 1.5, toThreshold: 0.5 },
      },
      rows: five.map((i, n) => ({
        instrument: i,
        weight: weights[n] ?? 0,
        target: 20,
        toThreshold: Math.round((2 - Math.abs((weights[n] ?? 0) - 20)) * 10) / 10,
      })),
      basisLine: {
        pendingBuyIncluded: false,
        fxRate: null,
        fxAt: null,
        withdrawExcluded: false,
        staleMarket: null,
        staleBasisDate: null,
      },
    };
    const base = planPaper();
    const plan: PlanResponse = {
      ...base,
      ruleShares: [...(base.ruleShares ?? []), { rule, pct: 10.0 }],
      rules: [...base.rules, fiveCard],
    };
    const bundle: FixtureBundle = {
      ...planPaperBundle,
      responses: { ...planPaperBundle.responses, '/api/plan': plan },
    };
    const cards = await openPlan(bundle);
    expect(cards).toHaveLength(3);
    const c = screen.getByRole('article', { name: '다섯 종목' });
    expect(c.querySelectorAll('line.needle')).toHaveLength(1);
    expect(within(c).getAllByRole('listitem')).toHaveLength(5);
    // The needle names the row furthest from its target (다: 21.5 vs 20 → +1.5%p).
    const deviations = weights.map((w) => Math.abs(w - 20));
    const furthest = five[deviations.indexOf(Math.max(...deviations))];
    expect(within(c).getByRole('img', { name: /%p/ }).getAttribute('aria-label')).toBe(
      `${furthest?.name ?? ''} +1.5%p · 리밸런싱까지 0.5%p`,
    );
    // Same frame as the others: head, status, gauge, rows, basis line.
    for (const a of cards) {
      expect(a.querySelector('h2')).not.toBeNull();
      expect(a.querySelector('svg[role="img"]')).not.toBeNull();
      expect(a.querySelector('ul')).not.toBeNull();
    }
  });
});
