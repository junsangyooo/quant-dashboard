// The words the screens make from the final contract's data (2026-10-09 '서버 문구 걷어냄'):
// metric names and margins, AI judgment items, '지금' kv rows, and the 작동 cards whose facts
// changed shape. Every copy string tested here is marked NEW in its copy file.
import { describe, expect, it } from 'vitest';
import { marginText, metricName } from '../../src/api/adapters';
import type { HealthResponse, JudgmentItem, Margin, MetricRef } from '../../src/api/types';
import { CELLTRION } from '../../src/fixtures/parts/day';
import { NVDA, SAMSUNG } from '../../src/fixtures/world';
import { judgmentItemText, judgmentLine, votesLabel } from '../../src/screens/Day/dayModel';
import { sourceView, todoView, tossFill } from '../../src/screens/Health/text';
import { kvView, orderText, periodText } from '../../src/screens/Rules/nowWords';

describe('metric names (CONTRACT MetricRef, autotrade/domain/metrics.py)', () => {
  it.each<[MetricRef, string]>([
    [{ key: 'revenue' }, '매출'],
    [{ key: 'operating_income' }, '영업이익'],
    [{ key: 'net_income' }, '순이익'],
    [{ key: 'op_margin' }, '이익률'],
    [{ key: 'eps' }, 'EPS'],
    [{ key: 'fcf' }, 'FCF'],
    [{ key: 'ebitda_margin' }, 'EBITDA 마진'],
    [{ key: 'net_debt_to_ebitda' }, '순부채/EBITDA'],
    [{ key: 'backlog' }, '수주잔고'],
    [{ key: 'new_orders' }, '신규 수주'],
    [{ key: 'book_to_bill' }, '수주/매출'],
    [{ key: 'monthly_revenue_yoy' }, '월매출 전년비'],
    [{ key: 'segment_revenue', param: 'AI' }, 'AI 매출'],
    [{ key: 'segment_operating_income', param: '전력기기' }, '전력기기 영업이익'],
    [{ key: 'segment_op_margin', param: '전력기기' }, '전력기기 이익률'],
    [{ key: 'segment_backlog', param: '지상방산' }, '지상방산 수주잔고'],
    [{ key: 'guidance', param: '2027 매출 성장' }, '2027 매출 성장'],
  ])('%o → %s', (metric, name) => {
    expect(metricName(metric)).toBe(name);
  });

  it('names a segment or guidance metric that came without the company word', () => {
    expect(metricName({ key: 'segment_backlog' })).toBe('부문 수주잔고');
    expect(metricName({ key: 'guidance', param: ' ' })).toBe('회사 전망');
  });
});

describe('margins (CONTRACT Margin)', () => {
  it.each<[Margin, string]>([
    [{ unit: 'pp', value: 2.3 }, '2.3%p'],
    [{ unit: 'pct', value: 2.1 }, '2.1%'],
    [{ unit: 'KRW', value: 3_100_000_000_000 }, '3.1조'],
    [{ unit: 'KRW', value: 3_000_000_000_000 }, '3조'],
    [{ unit: 'KRW', value: 450_000_000_000 }, '4,500억'],
    [{ unit: 'KRW', value: 4_550_000_000 }, '45.5억'],
    [{ unit: 'KRW', value: 35_000_000 }, '3,500만'],
    [{ unit: 'KRW', value: 9_500 }, '9,500원'],
    [{ unit: 'USD', value: 350_000_000 }, '$350M'],
    [{ unit: 'USD', value: 1_200_000_000 }, '$1.2B'],
    [{ unit: 'USD', value: 0.35 }, '$0.35'],
    [{ unit: 'KRW', value: -2_000_000_000_000 }, '−2조'],
    [{ unit: 'x', value: 0.12 }, '0.12x'],
    [{ unit: 'count', value: 3 }, '3'],
    [{ unit: 'quarter', value: 2 }, '2분기'],
    [{ unit: 'month', value: 3 }, '3개월'],
    [{ unit: 'year', value: 1 }, '1년'],
  ])('%o → %s', (margin, text) => {
    expect(marginText(margin)).toBe(text);
  });
});

describe('AI judgment items (CONTRACT JudgmentItem)', () => {
  it.each<[JudgmentItem, string]>([
    [{ key: 'instrument', instrument: CELLTRION }, '셀트리온'],
    [{ key: 'sold', instrument: SAMSUNG }, '팔 종목 삼성전자'],
    [{ key: 'bought', instrument: NVDA }, '살 종목 NVDA'],
    [{ key: 'shock', date: '2026-10-02', value: -8.1 }, '10/2 지수 대비 −8.1%'],
    [{ key: 'condition', value: 2 }, '반증 조건 2번'],
    [{ key: 'filing', date: '2026-09-30' }, '9/30 공시'],
    [{ key: 'review', value: 'invalidated' }, '월 점검 반증'],
    [{ key: 'review', value: 'weaken', months: 2 }, '월 점검 약화 2달째'],
    [{ key: 'month', value: '2026-10' }, '10월'],
    [{ key: 'cost', value: 0.35 }, '바꾸기 비용 0.35%'],
    [{ key: 'filings', value: 2 }, '최근 공시 2건'],
    [{ key: 'news', value: 3 }, '뉴스 3건'],
    [{ key: 'picks', value: 15 }, '보유 15종목'],
    [{ key: 'held', value: 12 }, '보유 12종목'],
    [{ key: 'candidates', value: 6 }, '후보 6종목'],
    [{ key: 'checks', value: 3 }, '살 조건 3개 충족'],
    [{ key: 'hold', value: 13 }, '유지 13'],
    [{ key: 'weaken', value: 2 }, '약화 2'],
    [{ key: 'invalidated', value: 0 }, '반증 0'],
    [{ key: 'rewritten', value: 1 }, '팔 조건 고침 1'],
    [{ key: 'new-picks', value: 4 }, '새 종목 4'],
    [{ key: 'expired', value: 1 }, '만료 후보 1'],
    [{ key: 'slot-full' }, '자리 없음 → 바꾸기 확인'],
  ])('%o → %s', (item, text) => {
    expect(judgmentItemText(item)).toBe(text);
  });

  it("joins a line with ' · ' and hides an empty one", () => {
    expect(
      judgmentLine([
        { key: 'month', value: '2026-11' },
        { key: 'picks', value: 15 },
      ]),
    ).toBe('11월 · 보유 15종목');
    expect(judgmentLine([])).toBeNull();
  });

  it("words the switch check's votes", () => {
    expect(votesLabel(['switch', 'switch'])).toBe("두 번 다 '바꾸기'");
    expect(votesLabel(['switch', 'keep'])).toBe("'바꾸기' · '그대로'");
  });
});

describe("'지금' kv rows (CONTRACT NowBlock kv keys)", () => {
  it.each<
    [
      string,
      string,
      string | undefined,
      { label: string | null; value: string; note: string | null },
    ]
  >([
    ['krClose', '2026-10-07', 'fresh', { label: '한국 종가', value: '10/7', note: '정상' }],
    ['usClose', '2026-10-02', 'stale', { label: '미국 종가', value: '10/2', note: '낡음' }],
    ['filings', 'HD현대일렉트릭', '1', { label: '공시', value: 'HD현대일렉트릭', note: '새 1' }],
    ['filings', '-', '0', { label: '공시', value: '—', note: '새 0' }],
    ['metricTable', '2026-10-06', '12', { label: '지표 표', value: '10/6', note: '12종목' }],
    ['metricTable', '-', '0', { label: '지표 표', value: '—', note: '0종목' }],
    ['hits', '0', undefined, { label: '걸린 종목', value: '0', note: null }],
    ['verdict', 'invalidated', 'filing', { label: '판정', value: '반증', note: '공시' }],
    ['judgments', '3', undefined, { label: '판단', value: '3', note: null }],
    [
      'votes',
      'hold,invalidated',
      undefined,
      { label: '두 번 확인', value: "'유지' · '반증'", note: null },
    ],
    ['tokens', '720000', undefined, { label: null, value: '약 72만 토큰', note: null }],
    ['picks', '15', undefined, { label: '보유', value: '15종목', note: null }],
    ['newFilings', '4', undefined, { label: '새 공시 · 30일', value: '4건', note: null }],
    ['lastDiscovery', '-', undefined, { label: '마지막 발굴', value: '—', note: null }],
    ['candidates', '6', undefined, { label: '후보 대기', value: '6종목', note: null }],
    ['targetEach', '6.7', undefined, { label: '종목당 목표', value: '6.7%', note: null }],
    ['someday', 'as sent', 'x', { label: 'someday', value: 'as sent', note: 'x' }],
  ])('%s %s %s', (key, value, note, view) => {
    expect(kvView(key, value, note)).toEqual(view);
  });

  it('words order rows and earnings periods', () => {
    expect(orderText('sell', '삼성전자')).toBe('매도 · 삼성전자');
    expect(orderText('fx', 'krw-usd')).toBe('환전 · 원 → 달러');
    expect(orderText('fx', 'usd-krw')).toBe('환전 · 달러 → 원');
    expect(periodText('2026Q3')).toBe('3Q');
    expect(periodText('FY2026')).toBe('FY2026');
  });
});

describe('작동 cards whose facts changed shape', () => {
  const NOW = '2026-10-07T16:10:00+09:00';
  const todo = (t: Partial<HealthResponse['todos'][number]>): HealthResponse['todos'][number] => ({
    id: 'x',
    severity: 'red',
    kind: 'ai-cli',
    facts: {},
    action: { kind: 'manual' },
    effect: 'other',
    ...t,
  });

  it('AI 호출 over budget is yellow with no time; failed tasks name the task and since', () => {
    const budget = todoView(
      todo({
        severity: 'yellow',
        facts: { reason: 'over-budget', tokens: 3_240_000, budget: 3_000_000 },
      }),
      NOW,
    );
    expect(budget.title).toBe('AI 토큰 예산 넘음');
    expect(budget.lines).toEqual([
      '이번 달 324만 토큰 · 예산 300만 토큰',
      'AI 판단은 그대로 돌아요',
    ]);
    const failed = todoView(
      todo({
        facts: {
          reason: 'task-failed',
          count: 2,
          taskKind: 'sell-confirm',
          since: '2026-10-07T06:00:00+09:00',
        },
      }),
      NOW,
    );
    expect(failed.title).toBe('AI 호출 실패 · 06:00부터');
    expect(failed.lines).toEqual([
      '팔기 확인 2건이 세 번 실패했어요',
      'Claude 구독 로그인 확인 요청',
    ]);
  });

  it('공시 stopped (not maintenance) and its last receipt', () => {
    const view = todoView(
      todo({
        kind: 'filings',
        facts: {
          source: 'edgar',
          market: 'US',
          state: 'stale',
          since: '2026-10-06T18:00:00+09:00',
        },
        action: { kind: 'auto-retry', at: '2026-10-08T08:30:00+09:00' },
      }),
      NOW,
    );
    expect(view.title).toBe('미국 공시 수집 멈춤');
    expect(view.lines).toEqual([
      '미국 공시 감시가 멈췄어요',
      '다음 확인 때 다시 받아요',
      '마지막으로 받음 10/6 18:00',
    ]);
  });

  it('공시 row names the stopped feed from extra { dart, edgar }', () => {
    const view = sourceView(
      {
        id: 'filings',
        state: 'maintenance',
        basis: '2026-10-06',
        receivedAt: '2026-10-06T18:00:00+09:00',
        cadence: 'event',
        age: 0.9,
        extra: { dart: 'maintenance', edgar: 'ok' },
      },
      NOW,
    );
    expect(view.line).toBe('한국 공시 감시 멈춤 · 10/6 18:00 받음');
  });

  it('토스 연결 age (days since connecting ÷ 90) puts the expiry at the late/stale edge', () => {
    expect(tossFill(0)).toBe(0);
    expect(tossFill(0.87)).toBeCloseTo(0.6525);
    expect(tossFill(1)).toBe(0.75);
    expect(tossFill(2)).toBe(1);
  });
});
