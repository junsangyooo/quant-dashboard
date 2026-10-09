// SCR-RULES responses (/api/rules, /api/rules/{id}?lane=) of the 예시-값표 worlds and of the
// 3년 발굴 proposal (Figma 탐색 17:5855 · 17:6432 · 17:7193 · 17:7808, 화면-맞춤.md §5–6).
// The flow cards' words are the rule definition's (data); the numbers are the table's for the
// two 모의투자 rules and illustrative for 3년 발굴 (as on the 탐색 page).
import type {
  FlowDisplay,
  Instrument,
  NowBlock,
  RuleDetailResponse,
  RulesListResponse,
  TilesDisplay,
} from '../../api/types';
import type {
  EdgeProposal,
  FlowEdge,
  KvRowProposal,
  NowBlockProposal,
  NowRow,
  OrderRowProposal,
  ProposedNode,
  TilesConditionProposal,
} from '../../screens/Rules/proposed';
import { BTC, INDEX_HALF, KOSPI200, MOMENTUM, NVDA, SAMSUNG, SP500, kst } from '../world';
import { PAPER_BUY_1007, PAPER_FX_1007, PAPER_SELL_1007, stages1007 } from './common';
import { CELLTRION, DISCOVERY } from './day';

// ── list ────────────────────────────────────────────────────────────────────

export function rulesList(
  momentum: RulesListResponse['rules'][number]['status'] = 'in-range',
  index: RulesListResponse['rules'][number]['status'] = 'in-progress',
): RulesListResponse {
  return {
    rules: [
      { rule: INDEX_HALF, share: { pct: 81.1, target: 80 }, status: index },
      { rule: MOMENTUM, share: { pct: 18.3, target: 20 }, status: momentum },
    ],
  };
}

export function rulesListDiscovery(): RulesListResponse {
  return {
    rules: [
      { rule: INDEX_HALF, share: { pct: 81.1, target: 80 }, status: 'in-progress' },
      { rule: DISCOVERY, share: { pct: 18.3, target: 20 }, status: 'hold' },
    ],
  };
}

// ── 지수 반반: 요약 타일 6칸 (Figma 1:61916 · 1:60971) ────────────────────────────

/** 과거 1년 수익 · 측정: 세후 중간값 +9.5%, 나쁜 해 −13.6%, 최악 −33.5%, 2015–25, T09. */
const MEASURED: NonNullable<TilesDisplay['measured']> = {
  median: 9.5,
  worst: -33.5,
  badYear: -13.6,
  period: '2015–25',
  afterTax: true,
  source: 'T09',
};

/** 조건 tile points (인계 '작은 불일치' 2): now +0.2%p (빈 점), 08:30 check +2.4%p (주황 점). */
const CONDITION_1007: TilesDisplay['condition'] & TilesConditionProposal = {
  threshold: 2,
  targetEach: [50, 50],
  deviation: { now: 0.2, atCheck: 2.4 },
};

function indexTiles(now: TilesDisplay['now'], condition: TilesDisplay['condition']): TilesDisplay {
  return {
    kind: 'tiles',
    what: { instruments: [KOSPI200, SP500], weights: [50, 50], basis: 'krw' },
    when: { time: '08:30', days: 'weekdays', tz: 'KST' },
    condition,
    action: { stages: ['sell', 'fx', 'buy'] },
    measured: MEASURED,
    now,
  };
}

export function ruleIndexHalf(): RuleDetailResponse {
  return {
    rule: INDEX_HALF,
    share: { pct: 81.1, target: 80 },
    status: 'in-progress',
    example: true,
    display: indexTiles(
      {
        status: 'in-progress',
        stages: stages1007(PAPER_SELL_1007, PAPER_FX_1007, PAPER_BUY_1007),
        nextCheckAt: kst('2026-10-08', '08:30'),
      },
      CONDITION_1007,
    ),
  };
}

/** 출시 첫날 (값표 §4, Figma 1:61661): 자산의 99.6% · 목표 100%, 환전 09:10 ✓ · 매수 22:30 ⏳. */
export function ruleIndexFirstDay(): RuleDetailResponse {
  const condition: TilesDisplay['condition'] & TilesConditionProposal = {
    threshold: 2,
    targetEach: [50, 50],
    deviation: { now: 0.2, atCheck: null },
  };
  return {
    rule: INDEX_HALF,
    share: { pct: 99.6, target: 100 },
    status: 'in-progress',
    example: true,
    display: indexTiles(
      {
        status: 'in-progress',
        stages: [
          { kind: 'fx', status: 'done', at: kst('2026-07-01', '09:10'), orders: [] },
          { kind: 'buy', status: 'pending', at: kst('2026-07-01', '22:30'), orders: [] },
        ],
        nextCheckAt: kst('2026-07-02', '08:30'),
      },
      condition,
    ),
  };
}

/** 시세 대기 (값표 §3): no 10/7 rebalance; status '시세 대기', points hidden. */
export function ruleIndexStale(): RuleDetailResponse {
  const base = ruleIndexHalf();
  return {
    ...base,
    status: 'quote-wait',
    display: indexTiles(
      { status: 'quote-wait', stages: null, nextCheckAt: kst('2026-10-08', '08:30') },
      CONDITION_1007,
    ),
  };
}

// ── flow helpers ────────────────────────────────────────────────────────────

type Node = ProposedNode;

function now(
  headKey: NowBlock['headKey'],
  rows: NowRow[],
  extra: Partial<NowBlock & NowBlockProposal> = {},
): NowBlock {
  const block: NowBlock & NowBlockProposal = { headKey, rows, ...extra };
  return block;
}

function kv(key: string, value: string, note?: string): NowRow {
  const row: Extract<NowRow, { kind: 'kv' }> & KvRowProposal = { kind: 'kv', key, value, note };
  return row;
}

function inst(
  instrument: Instrument,
  extra: Omit<Extract<NowRow, { kind: 'instrument' }>, 'kind' | 'instrument'> = {},
): NowRow {
  return { kind: 'instrument', instrument, ...extra };
}

function edge(
  from: string,
  to: string,
  style: FlowEdge['style'],
  label?: FlowEdge['label'],
): FlowEdge {
  return label ? { from, to, style, label } : { from, to, style };
}

const EXCEPTIONS: NowRow = {
  kind: 'exceptions',
  items: ['holiday', 'quote-wait', 'withdraw-wait'],
  active: false,
};

// ── [예시] 종목 모멘텀: 노드 카드 9종 (Figma 1:62197 · 1:61226, 값표 §1.1 · §1.3) ─────────

function momentumFlow(): FlowDisplay {
  const retried: Extract<NowRow, { kind: 'order' }> & OrderRowProposal = {
    kind: 'order',
    side: 'buy',
    text: '매수 1 · BTC',
    status: 'filled',
    at: kst('2026-09-15', '09:02'),
    retried: true,
  };
  const nodes: Node[] = [
    {
      id: 'start',
      type: 'start',
      col: 0,
      row: 0,
      title: '매일 08:30',
      subtitle: '한국 시간 · 평일',
      now: now('now', [], { at: kst('2026-10-08', '08:30') }),
    },
    {
      id: 'stock',
      type: 'stock',
      col: 1,
      row: 0,
      title: '후보군 8종목',
      more: 5,
      now: now('now', [
        inst(SAMSUNG, { weight: 42.0, ret: 1.4 }),
        inst(NVDA, { weight: 39.0, ret: 1.7 }),
        inst(BTC, { weight: 18.9, ret: -15.1 }),
      ]),
    },
    {
      id: 'data',
      type: 'data',
      col: 2,
      row: 0,
      title: '30일 수익률',
      subtitle: '종목마다 · 어제 종가 기준',
      now: now(
        'now',
        [
          { kind: 'rank', rank: 1, instrument: SAMSUNG, ret: 6.2 },
          { kind: 'rank', rank: 2, instrument: NVDA, ret: 4.8 },
          { kind: 'rank', rank: 3, instrument: BTC, ret: 0.9 },
        ],
        { note: '8종목 중 상위 3' },
      ),
    },
    {
      id: 'ai',
      type: 'ai',
      col: 0,
      row: 1,
      title: '상위 3 고르고 비중 정하기',
      fields: [
        { key: 'input', value: '8종목 · 30일 수익률' },
        { key: 'ai', value: '상위 3 고르고 비중' },
        { key: 'output', value: '3종목 · 비중' },
      ],
      now: now(
        'now-last-judgment',
        [inst(SAMSUNG), inst(NVDA), inst(BTC), kv('', '지난번과 같은 3종목')],
        {
          at: kst('2026-10-07', '08:30'),
        },
      ),
    },
    {
      id: 'weight',
      type: 'weight',
      col: 1,
      row: 1,
      title: '42 · 40 · 18',
      subtitle: '규칙 안 비중',
      targets: [
        { instrument: SAMSUNG, weight: 42 },
        { instrument: NVDA, weight: 40 },
        { instrument: BTC, weight: 18 },
      ],
      now: now('now', [
        inst(SAMSUNG, { weight: 42.0 }),
        inst(NVDA, { weight: 39.0 }),
        inst(BTC, { weight: 18.9 }),
      ]),
    },
    {
      id: 'condition',
      type: 'condition',
      col: 2,
      row: 1,
      title: '2%p 넘게 벗어났나요?',
      subtitle: '목표 비중과 지금 비중 비교',
      now: now('now-check', [{ kind: 'band', value: 1.0, threshold: 2, instrument: BTC }], {
        at: kst('2026-10-07', '08:30'),
      }),
    },
    {
      id: 'action',
      type: 'action',
      col: 0,
      row: 2,
      title: '리밸런싱 주문',
      now: now(
        'now-last',
        [
          {
            kind: 'order',
            side: 'sell',
            text: '매도 1 · 삼성전자',
            status: 'filled',
            at: kst('2026-09-14', '09:05'),
          },
          { kind: 'order', side: 'fx', text: '환전 없음 · 코인은 원화' },
          retried,
        ],
        { at: '2026-09-14', until: '2026-09-15' },
      ),
    },
    {
      id: 'result',
      type: 'result',
      col: 2,
      row: 2,
      title: '리밸런싱 상태',
      subtitle: '지금 상태 · 마지막 실행',
      now: now('now', [{ kind: 'status', status: 'in-range', at: kst('2026-10-07', '08:30') }]),
    },
    {
      id: 'exception',
      type: 'exception',
      col: 0,
      row: 3,
      title: '다음 확인으로 미룸',
      now: now('now', [EXCEPTIONS]),
    },
  ];
  return {
    kind: 'flow',
    lanes: [{ id: 'daily', label: { kind: 'daily', time: '08:30' } }],
    lane: 'daily',
    nodes,
    edges: [
      edge('start', 'stock', 'taken'),
      edge('stock', 'data', 'taken'),
      edge('data', 'ai', 'taken'),
      edge('ai', 'weight', 'taken'),
      edge('weight', 'condition', 'taken'),
      edge('condition', 'action', 'not-taken', 'yes'),
      edge('condition', 'result', 'taken', 'no-keep'),
      edge('action', 'result', 'not-taken'),
      edge('action', 'exception', 'exception'),
    ],
  };
}

export function ruleMomentum(
  status: RuleDetailResponse['status'] = 'in-range',
): RuleDetailResponse {
  return {
    rule: MOMENTUM,
    share: { pct: 18.3, target: 20 },
    status,
    example: true,
    display: momentumFlow(),
  };
}

// ── 3년 발굴: 흐름 넷 (탐색 17:5855 매일 · 17:7193 실적 · 17:7808 매달 · 17:6432 분기) ───────

const HD: Instrument = {
  id: 'KR:267260',
  name: 'HD현대일렉트릭',
  kind: 'stock',
  market: 'KR',
  currency: 'KRW',
  initials: 'HD',
};
const HANWHA_AERO: Instrument = {
  id: 'KR:012450',
  name: '한화에어로',
  kind: 'stock',
  market: 'KR',
  currency: 'KRW',
  initials: '한',
};
const BROADCOM: Instrument = {
  id: 'US:AVGO',
  name: 'Broadcom',
  kind: 'stock',
  market: 'US',
  currency: 'USD',
  initials: 'AV',
};

const LANES: FlowDisplay['lanes'] = [
  { id: 'daily', label: { kind: 'daily', time: '08:30' } },
  { id: 'earnings', label: { kind: 'earnings' } },
  { id: 'monthly', label: { kind: 'monthly' } },
  { id: 'quarterly', label: { kind: 'quarterly' } },
];

function discoveryDaily(): FlowDisplay {
  const nodes: Node[] = [
    {
      id: 'start',
      type: 'start',
      col: 0,
      row: 0,
      title: '매일 08:30',
      subtitle: '한국 시간 · 평일',
      now: now('now', [], { at: kst('2026-10-08', '08:30') }),
    },
    {
      id: 'data',
      type: 'data',
      col: 1,
      row: 0,
      title: '시세 · 새 공시 · 지표 표',
      subtitle: '종가·환율 · DART·EDGAR',
      now: now(
        'now-check',
        [
          kv('시세', '한국 10/7 · 미국 10/6', '정상'),
          kv('공시', 'HD현대일렉트릭 3Q', '새 1'),
          kv('지표', '15종목 중 12 최신', '—'),
        ],
        { at: kst('2026-10-07', '08:30') },
      ),
    },
    {
      id: 'condition',
      type: 'condition',
      col: 2,
      row: 0,
      title: '팔·살 조건에 걸렸나요?',
      subtitle: '팔 조건 · 급락 · 관련 공시 · 살 값',
      now: now('now-check', [inst(HD, { progress: 54, marginText: '여유 2.3%p' })], {
        at: kst('2026-10-07', '08:30'),
      }),
    },
    {
      id: 'ai',
      type: 'ai',
      col: 0,
      row: 1,
      title: '근거가 깨졌나요?',
      fields: [
        { key: 'input', value: '걸린 종목 자료 · 최근 공시' },
        { key: 'ai', value: 'Sonnet · 두 번 묻기' },
        { key: 'output', value: '유지 · 약화 · 반증' },
      ],
      now: now(
        'now-last-judgment',
        [inst(CELLTRION, { marginText: '급락 확인' }), kv('', "두 번 다 '유지' · 팔지 않음")],
        { at: kst('2026-10-02', '08:34') },
      ),
    },
    {
      id: 'confirm',
      type: 'condition',
      col: 1,
      row: 1,
      title: "둘 다 '반증'인가요?",
      subtitle: "사는 쪽은 한 번 '근거 있음'이면 삼",
      now: now('now-month', [kv('', '판단 1 · 유지', '매도 0 · 매수 0')]),
    },
    {
      id: 'result',
      type: 'result',
      col: 2,
      row: 1,
      title: '보유 유지',
      subtitle: '팔 조건 밖 · 마지막 확인',
      now: now('now', [{ kind: 'status', status: 'hold', at: kst('2026-10-07', '08:30') }]),
    },
    {
      id: 'action',
      type: 'action',
      col: 1,
      row: 2,
      title: '매도 · 판 돈은 지수 ETF로',
      now: now('now-month', [
        { kind: 'order', side: 'sell', text: '매도 0건' },
        { kind: 'order', side: 'fx', text: '환전 없음 · 같은 나라 ETF' },
        { kind: 'order', side: 'buy', text: '매수 0건 · 후보 살 값' },
      ]),
    },
    {
      id: 'exception',
      type: 'exception',
      col: 1,
      row: 3,
      title: '다음 확인으로 미룸',
      now: now('now', [EXCEPTIONS]),
    },
  ];
  return {
    kind: 'flow',
    lanes: LANES,
    lane: 'daily',
    nodes,
    edges: [
      edge('start', 'data', 'taken'),
      edge('data', 'condition', 'taken'),
      edge('condition', 'ai', 'not-taken', 'yes'),
      edge('condition', 'result', 'taken', 'no-keep'),
      edge('ai', 'confirm', 'not-taken'),
      edge('confirm', 'result', 'not-taken', 'no'),
      edge('confirm', 'action', 'not-taken', 'yes'),
      edge('action', 'exception', 'exception'),
    ],
  };
}

function discoveryQuarterly(): FlowDisplay {
  const noWait: FlowEdge & EdgeProposal = {
    from: 'condition',
    to: 'result',
    style: 'taken',
    labelKey: 'no-wait',
  };
  const nodes: Node[] = [
    {
      id: 'start',
      type: 'start',
      col: 0,
      row: 0,
      title: '4·6·9·12월 1일',
      subtitle: '실적 공시가 다 나온 뒤',
      now: now('now', [], { at: '2026-12-01' }),
    },
    {
      id: 'data',
      type: 'data',
      col: 1,
      row: 0,
      title: '거시 · 흐름 · 실적 · 값',
      subtitle: '금리·환율·업종 흐름·후보 재무',
      now: now(
        'now',
        [
          kv('거시', '금리·환율·물가', '갱신'),
          kv('흐름', '6~8개 · 확인·반증 조건', '갱신'),
          kv('후보', '실적에 흐름이 보임', '40여'),
        ],
        { note: '기준 전날' },
      ),
    },
    {
      id: 'ai',
      type: 'ai',
      col: 2,
      row: 0,
      title: '흐름과 기업 고르기',
      more: 12,
      fields: [
        { key: 'input', value: '거시 · 흐름 · 후보 실적' },
        { key: 'ai', value: 'Opus · 웹 검색' },
        { key: 'output', value: '종목 · 팔 조건 · 살 조건' },
      ],
      now: now(
        'now-last-judgment',
        [inst(HD), inst(HANWHA_AERO), inst(BROADCOM), kv('', '후보 6 · 약 72만 토큰')],
        { at: '2026-10-07' },
      ),
    },
    {
      id: 'stock',
      type: 'stock',
      col: 0,
      row: 1,
      title: '보유 15 · 후보 6',
      more: 12,
      now: now('now', [
        inst(HD, { weight: 6.9, ret: 3.2 }),
        inst(HANWHA_AERO, { weight: 6.6, ret: -1.1 }),
        inst(BROADCOM, { weight: 6.8, ret: 2.4 }),
      ]),
    },
    {
      id: 'weight',
      type: 'weight',
      col: 1,
      row: 1,
      title: '같은 금액 · 종목당 6.7%',
      subtitle: '확신으로 나누지 않음',
      more: 12,
      now: now('now', [
        inst(HD, { weight: 6.9 }),
        inst(HANWHA_AERO, { weight: 6.6 }),
        inst(BROADCOM, { weight: 6.8 }),
        kv('', '목표 6.7%씩 · 고를 때만 맞춤'),
      ]),
    },
    {
      id: 'condition',
      type: 'condition',
      col: 2,
      row: 1,
      title: '살 값에 왔나요?',
      subtitle: '후보마다 살 조건 · 매일 확인',
      now: now('now-check', [kv('', '한화오션 살 값까지', '4.1%')], {
        at: kst('2026-10-07', '08:30'),
      }),
    },
    {
      id: 'action',
      type: 'action',
      col: 0,
      row: 2,
      title: '새 종목 매수',
      now: now(
        'now',
        [
          { kind: 'order', side: 'sell', text: '매도 없음' },
          { kind: 'order', side: 'fx', text: '환전 1 · 원 → 달러' },
          { kind: 'order', side: 'buy', text: '매수 9 · 같은 금액', status: 'filled' },
        ],
        { note: '10/7 발굴 뒤' },
      ),
    },
    {
      id: 'result',
      type: 'result',
      col: 2,
      row: 2,
      title: '후보로 대기',
      subtitle: '살 값이 오면 매일 확인에서 삼',
      now: now('now', [kv('', '대기 6')]),
    },
    {
      id: 'exception',
      type: 'exception',
      col: 0,
      row: 3,
      title: '다음 확인으로 미룸',
      now: now('now', [EXCEPTIONS]),
    },
  ];
  return {
    kind: 'flow',
    lanes: LANES,
    lane: 'quarterly',
    nodes,
    edges: [
      edge('start', 'data', 'taken'),
      edge('data', 'ai', 'taken'),
      edge('ai', 'stock', 'taken'),
      edge('stock', 'weight', 'taken'),
      edge('weight', 'condition', 'taken'),
      edge('condition', 'action', 'not-taken', 'yes'),
      noWait,
      edge('action', 'result', 'not-taken'),
      edge('action', 'exception', 'exception'),
    ],
  };
}

function discoveryEarnings(): FlowDisplay {
  const nodes: Node[] = [
    {
      id: 'start',
      type: 'start',
      col: 0,
      row: 0,
      title: '실적 공시가 나오면',
      subtitle: 'DART · EDGAR · 매일 확인',
      now: now('now', [kv('', 'HD현대일렉트릭')], { at: '2026-10-24' }),
    },
    {
      id: 'ai',
      type: 'ai',
      col: 1,
      row: 0,
      title: '실적 지표 뽑기',
      fields: [
        { key: 'input', value: '공시 원문' },
        { key: 'ai', value: 'Haiku' },
        { key: 'output', value: '지표 · 값 · 근거 문장' },
      ],
      now: now(
        'now-last',
        [inst(CELLTRION, { marginText: '2Q · 6개' }), kv('', '틀린 값 0 · 회당 0.2센트')],
        { at: '2026-10-06' },
      ),
    },
    {
      id: 'data',
      type: 'data',
      col: 2,
      row: 0,
      title: '지표 표',
      subtitle: '종목 · 지표 · 값 · 기간 · 출처',
      now: now(
        'now',
        [
          kv('HD', '수주잔고 · 2Q', '갱신'),
          kv('셀', '영업이익 목표 · 3Q', '갱신'),
          kv('AV', 'AI 매출 · FQ3', '대기'),
        ],
        { note: '15종목' },
      ),
    },
    {
      id: 'result',
      type: 'result',
      col: 0,
      row: 1,
      title: '매일 확인에서 대조',
      subtitle: '팔 조건 · 계획 게이지에 반영',
      now: now('now', [{ kind: 'status', status: 'hold', at: '2026-10-06' }]),
    },
  ];
  return {
    kind: 'flow',
    lanes: LANES,
    lane: 'earnings',
    nodes,
    edges: [
      edge('start', 'ai', 'taken'),
      edge('ai', 'data', 'taken'),
      edge('data', 'result', 'taken'),
    ],
  };
}

function discoveryMonthly(): FlowDisplay {
  const nodes: Node[] = [
    {
      id: 'start',
      type: 'start',
      col: 0,
      row: 0,
      title: '매달 1일',
      subtitle: '전날 밤 · 보유 종목 전부',
      now: now('now', [], { at: '2026-11-01' }),
    },
    {
      id: 'data',
      type: 'data',
      col: 1,
      row: 0,
      title: '자료 꾸러미',
      subtitle: '가격 · 재무 · 지표 표 · 최근 공시',
      now: now(
        'now',
        [
          kv('가격', '지수 대비 · 고른 날부터', '15'),
          kv('재무', '분기 실적 · 값', '15'),
          kv('공시', '지난달 새 공시', '4'),
        ],
        { note: '종목당 약 6천 토큰' },
      ),
    },
    {
      id: 'ai',
      type: 'ai',
      col: 2,
      row: 0,
      title: '유지 · 약화 · 반증',
      fields: [
        { key: 'input', value: '종목마다 자료 꾸러미' },
        { key: 'ai', value: 'Sonnet · 사고량 낮음' },
        { key: 'output', value: '판정 · 팔 조건 고쳐 쓰기' },
      ],
      now: now(
        'now-last-judgment',
        [kv('', '유지 13 · 약화 2 · 반증 0'), kv('', '15종목 약 12만 토큰')],
        { at: '2026-10-01' },
      ),
    },
    {
      id: 'result',
      type: 'result',
      col: 0,
      row: 1,
      title: '반증이면 매일 흐름의 두 번 확인으로',
      subtitle: '약화 두 달 연속도 같은 길',
      now: now('now', [{ kind: 'status', status: 'hold', at: '2026-10-01' }]),
    },
  ];
  return {
    kind: 'flow',
    lanes: LANES,
    lane: 'monthly',
    nodes,
    edges: [
      edge('start', 'data', 'taken'),
      edge('data', 'ai', 'taken'),
      edge('ai', 'result', 'taken'),
    ],
  };
}

const DISCOVERY_LANES = {
  daily: discoveryDaily,
  earnings: discoveryEarnings,
  monthly: discoveryMonthly,
  quarterly: discoveryQuarterly,
} as const;

export type DiscoveryLane = keyof typeof DISCOVERY_LANES;

export function ruleDiscovery(lane: DiscoveryLane): RuleDetailResponse {
  return {
    rule: DISCOVERY,
    share: { pct: 18.3, target: 20 },
    status: 'hold',
    example: true,
    display: DISCOVERY_LANES[lane](),
  };
}

/** /api/rules/discovery_3y (default lane) and one ?lane= key per lane. */
export function discoveryResponses(defaultLane: DiscoveryLane) {
  return {
    '/api/rules/discovery_3y': ruleDiscovery(defaultLane),
    '/api/rules/discovery_3y?lane=daily': ruleDiscovery('daily'),
    '/api/rules/discovery_3y?lane=earnings': ruleDiscovery('earnings'),
    '/api/rules/discovery_3y?lane=monthly': ruleDiscovery('monthly'),
    '/api/rules/discovery_3y?lane=quarterly': ruleDiscovery('quarterly'),
  } as const;
}
