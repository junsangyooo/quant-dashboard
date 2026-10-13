// The words the screens make from the final contract's data (2026-10-09 '서버 문구 걷어냄'):
// metric names and margins, AI judgment items, '지금' kv rows, and the 작동 cards whose facts
// changed shape. Every copy string tested here is marked NEW in its copy file.
import { describe, expect, it } from 'vitest';
import {
  fxMixText,
  fxSuggestionText,
  marginText,
  metricName,
  newMoneyText,
  ruleStatusChip,
} from '../../src/api/adapters';
import type {
  FxSuggestion,
  HealthResponse,
  JudgmentItem,
  Margin,
  MetricRef,
} from '../../src/api/types';
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

  it("words the buy check's two answers (asked twice since the audit of 10/10)", () => {
    expect(votesLabel(['buy', 'buy'])).toBe("두 번 다 '근거 있음'");
    expect(votesLabel(['buy', 'skip'])).toBe("'근거 있음' · '근거 없음'");
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

  it("the AI runner's heartbeat cards: no CLI, a long call, a waiting queue", () => {
    const missing = todoView(
      todo({
        id: 'ai-cli:missing',
        facts: { reason: 'cli-missing', since: '2026-10-07T06:00:00+09:00' },
      }),
      NOW,
    );
    expect(missing.title).toBe('Claude CLI 없음');
    expect(missing.lines).toEqual([
      '06:00부터 못 찾았어요',
      'AI 일감은 시도로 세지 않고 기다려요',
      '서버의 claude 설치와 cron 줄 확인 요청',
    ]);
    const running = todoView(
      todo({
        severity: 'yellow',
        facts: {
          reason: 'call-running',
          taskKind: 'discovery',
          since: '2026-10-07T14:05:00+09:00',
        },
      }),
      NOW,
    );
    expect(running.title).toBe('분기 발굴 호출이 14:05부터 이어져요');
    expect(running.lines).toEqual([
      '시간 상한은 없어서 그대로 기다려요',
      '너무 길면 서버의 claude 상태 확인 요청',
    ]);
    const queue = (cause: string) =>
      todoView(
        todo({
          severity: 'yellow',
          facts: { reason: 'queue-waiting', count: 3, since: '2026-10-06T22:00:00+09:00', cause },
        }),
        NOW,
      );
    expect(queue('off').title).toBe('AI 일감 3건이 기다려요');
    expect(queue('off').lines).toEqual(['AI 호출이 꺼져 있어요', '가장 오래된 일감 10/6 22:00']);
    expect(queue('stopped').lines[0]).toBe('AI 실행기가 돌지 않아요 · cron 확인 요청');
    expect(queue('busy').lines[0]).toBe('긴 호출 하나가 실행기를 잡고 있어요');
    expect(queue('cli-missing').lines[0]).toBe('Claude CLI를 찾지 못했어요');
    expect(queue('deferred').lines[0]).toBe('출처·키·자료를 기다려요');
    expect(queue('later').lines).toEqual(['가장 오래된 일감 10/6 22:00']);
  });

  it("공시 키 없음 is a person's card", () => {
    const view = todoView(
      todo({ kind: 'filings', facts: { source: 'dart', market: 'KR', state: 'no-key' } }),
      NOW,
    );
    expect(view.title).toBe('한국 공시 키 없음');
    expect(view.lines).toEqual([
      '한국 공시 원문을 읽을 키가 없어요',
      '서버 cron 줄의 키 파일 확인 요청',
    ]);
  });

  it('AI 호출 row says when there is no CLI', () => {
    const view = sourceView(
      {
        id: 'ai-cli',
        state: 'stale',
        basis: 'sonnet',
        receivedAt: '2026-10-07T08:35:00+09:00',
        cadence: 'event',
        age: 0,
        extra: { monthTokens: 8800, budget: 600000, enabled: 1, due: 2, cli: 'missing' },
      },
      NOW,
    );
    expect(view.line).toBe('Claude CLI 없음 · 마지막 성공 08:35 · 생길 때마다');
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

  it('PIN 실패 급증: since, the count and the last one, and whether new logins are closed', () => {
    const open = todoView(
      todo({
        kind: 'pin-failures',
        facts: {
          since: '2026-10-07T03:12:00+09:00',
          count: 12,
          lastAt: '2026-10-07T03:40:00+09:00',
          closed: 0,
        },
      }),
      NOW,
    );
    expect(open.tone).toBe('error');
    expect(open.icon).toBe('pin');
    expect(open.chip).toBe('직접 할 일');
    expect(open.title).toBe('PIN 실패 급증 · 03:12부터');
    expect(open.lines).toEqual(['틀린 PIN 12회 · 마지막 03:40', '새 로그인은 아직 열려 있어요']);
    expect(open.result).toBe('Claude에게 서버에서 unlock 요청 · 그러면 이 카드도 사라져요');
    const closed = todoView(
      todo({
        kind: 'pin-failures',
        facts: { since: '2026-10-06T23:00:00+09:00', count: 30, closed: 1 },
      }),
      NOW,
    );
    expect(closed.title).toBe('PIN 실패 급증 · 10/6 23:00부터');
    expect(closed.lines).toEqual([
      '틀린 PIN 30회',
      '새 로그인이 닫혔어요 · 열린 기기는 그대로 써요',
    ]);
    expect(todoView(todo({ kind: 'pin-failures', facts: {} }), NOW).title).toBe('PIN 실패 급증');
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

describe('작동 cards of the live link (3단계, autotrade/PHASE3.md 2.7)', () => {
  const NOW = '2026-07-01T09:20:00+09:00';
  const todo = (t: Partial<HealthResponse['todos'][number]>): HealthResponse['todos'][number] => ({
    id: 'x',
    severity: 'red',
    kind: 'toss-link',
    facts: {},
    action: { kind: 'manual' },
    effect: 'orders-zero-live-blocked',
    ...t,
  });

  it('토스 연결 names the cause and what to do; a passing cause retries by itself', () => {
    const ip = todoView(todo({ facts: { cause: 'ip' } }), NOW);
    expect(ip.title).toBe('토스 연결 · 허용 IP 아님');
    expect(ip.lines).toEqual(['토스가 서버 IP를 막았어요', '토스 WTS 허용 IP에 서버 주소 추가']);
    expect([ip.tone, ip.icon, ip.chip, ip.result]).toEqual([
      'error',
      'link',
      '직접 할 일',
      '그동안 주문 0건 · 실전 켜기 막힘',
    ]);
    const down = todoView(
      todo({
        severity: 'yellow',
        facts: { cause: 'maintenance' },
        action: { kind: 'auto-retry', at: '2026-07-01T09:25:00+09:00' },
      }),
      NOW,
    );
    expect(down.title).toBe('토스 연결 · 토스 점검 중');
    expect(down.chip).toBe('09:25 자동 재시도');
    expect(down.tone).toBe('warn');
    // A cause this screen does not know is not shown raw.
    expect(todoView(todo({ facts: { cause: 'new-cause' } }), NOW).title).toBe('토스 연결 · —');
    // An armed 조건주문 (the old quant's): cancel it in the Toss app before live is turned on.
    const armed = todoView(todo({ facts: { cause: 'conditional' } }), NOW);
    expect(armed.title).toBe('토스 연결 · 열린 조건주문');
    expect(armed.lines).toEqual([
      '토스에 감시 중인 조건주문이 있어요 · 조건이 되면 스스로 주문해요',
      '토스 앱에서 조건주문 취소',
    ]);
  });

  it('토스 잔고 불일치 says what differs; an order whose result is unknown says where', () => {
    const qty = todoView(
      todo({
        kind: 'broker-mismatch',
        facts: {
          reason: 'positions',
          instrument: 'KOSPI200 ETF',
          ledgerQty: '0',
          brokerQty: '3',
          count: 2,
        },
      }),
      NOW,
    );
    expect(qty.title).toBe('토스 잔고와 장부가 달라요');
    expect(qty.lines).toEqual([
      'KOSPI200 ETF 장부 0주 · 토스 3주 외 1종목',
      '토스 앱에서 확인 뒤 Claude에게 장부 맞추기 요청',
    ]);
    expect([qty.icon, qty.result]).toEqual(['mismatch', '그동안 주문 0건 · 실전 켜기 막힘']);
    const cash = todoView(
      todo({ kind: 'broker-mismatch', facts: { reason: 'cash', currency: 'USD' } }),
      NOW,
    );
    expect(cash.lines[0]).toBe('USD 현금이 장부로 설명되지 않게 바뀌었어요');
    const fill = todoView(
      todo({
        kind: 'broker-mismatch',
        facts: { reason: 'fractional', instrument: 'S&P 500 ETF' },
      }),
      NOW,
    );
    expect(fill.lines[0]).toBe('S&P 500 ETF 체결을 장부에 맞출 수 없어요');
    expect(
      todoView(todo({ kind: 'broker-mismatch', facts: { reason: 'other' } }), NOW).lines[0],
    ).toBe('장부로 설명되지 않는 차이가 있어요');
    const unknown = todoView(
      todo({
        kind: 'broker-mismatch',
        facts: { reason: 'order-unknown', market: 'KR', side: 'buy' },
      }),
      NOW,
    );
    expect(unknown.title).toBe('한국 매수 주문 결과 모름');
    expect(unknown.lines).toEqual([
      '토스에 이 주문으로 보이는 주문이 여럿이라 어느 것인지 몰라요',
      '토스 앱에서 어느 주문인지 확인 뒤 Claude에게 서버에서 정리 요청',
    ]);
  });

  it('no 토스 앱 환전 to-do any more: the live ledger never converts (D47)', () => {
    const kinds: HealthResponse['todos'][number]['kind'][] = ['toss-link', 'broker-mismatch'];
    expect(kinds).not.toContain('fx-manual');
  });

  it('토스 연결 row: the account and the last check, or the cause and the last success', () => {
    const base = {
      id: 'toss-link',
      state: 'fresh',
      basis: null,
      receivedAt: '2026-07-01T09:15:00+09:00',
      cadence: 'per-check',
      age: 0.33,
    } as const;
    const ok = sourceView({ ...base, extra: { account: '8901' } }, NOW);
    expect([ok.line, ok.chip, ok.fill]).toEqual([
      '계좌 끝 8901 · 09:15 확인 · 확인마다',
      '제때',
      0.165,
    ]);
    const late = sourceView(
      { ...base, state: 'late', basis: '2026-07-10', extra: { account: '8901', daysLeft: 9 } },
      NOW,
    );
    expect([late.line, late.chip]).toEqual([
      '만료 7/10 · 9일 남음 · 09:15 확인 · 확인마다',
      '만료 9일 전',
    ]);
    const broken = sourceView({ ...base, state: 'stale', age: 2.4, extra: { cause: 'ip' } }, NOW);
    expect([broken.line, broken.chip, broken.fill]).toEqual([
      '허용 IP 아님 · 마지막 성공 09:15 · 확인마다',
      '낡음',
      1,
    ]);
  });
});

describe('원화 · 달러 (D47·D48: the money as deposited, information only)', () => {
  const suggestion: FxSuggestion = {
    direction: 'krw-usd',
    krw: 5_000_000,
    usd: 3591.95,
    rate: 1392,
    now: { kr: 100, us: 0 },
    target: { kr: 50, us: 50 },
  };

  it('says how much to convert for the targets, in the currency the owner pays', () => {
    expect(fxSuggestionText(suggestion)).toBe('약 5,000,000원을 달러로 바꾸면 50:50');
    expect(fxMixText(suggestion)).toBe('지금 한국 100 : 미국 0');
    const back: FxSuggestion = {
      ...suggestion,
      direction: 'usd-krw',
      krw: 2_000_000,
      usd: 1436.78,
      now: { kr: 30.4, us: 69.6 },
    };
    expect(fxSuggestionText(back)).toBe('약 $1,437을 원화로 바꾸면 50:50');
    expect(fxMixText(back)).toBe('지금 한국 30.4 : 미국 69.6');
    expect(fxSuggestionText({ ...back, usd: 1432 })).toBe('약 $1,432를 원화로 바꾸면 50:50');
  });

  it('says when the money of today is used', () => {
    const from = '2026-10-08T08:30:00+09:00';
    expect(newMoneyText({ krw: 3_000_000, usd: 0, from })).toBe(
      '새로 들어온 돈 3,000,000원 · 다음 거래일 08:30부터 써요',
    );
    expect(newMoneyText({ krw: 1_000_000, usd: 718.39, from })).toBe(
      '새로 들어온 돈 1,000,000원 · $718.39 · 다음 거래일 08:30부터 써요',
    );
  });

  it('is a chip of its own, after 리밸런싱 예정 (a hollow accent dot)', () => {
    expect(ruleStatusChip('fx-suggest')).toEqual({ state: 'fxSuggest', label: '환전 제안' });
  });
});
