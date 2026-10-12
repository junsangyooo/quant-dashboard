// SCR-HOME copy. Sources: 기획.md §5 SCR-HOME (섹션·상태 표·문구 예), the Figma 디자인
// SCR-HOME frames, 예시-값표. Labels are short nouns; sentences use 해요체. The 계획 card shares
// its words with SCR-PLAN (copy/plan.ts).

export const homeCopy = {
  /** First load failed with nothing to show (pattern of copy.state.errors). */
  errors: { load: '자산을 못 불러왔어요' },

  hero: {
    /** '모의투자 자산 · 7/1부터' */
    assets: (ledger: string) => `${ledger} 자산`,
    since: (date: string) => `${date}부터`,
    /** 실전 첫 체결 전: '실전 자산 · 9/1 시작' */
    started: (date: string) => `${date} 시작`,
    /** 첫 확인 전: '모의투자 시작 금액' */
    startAmount: (ledger: string) => `${ledger} 시작 금액`,
    basis: (time: string) => `${time} 기준`,
    pnl: (amount: string, pct: string | null) => (pct === null ? amount : `${amount} · ${pct}`),
    pnlAfterFirstFill: '손익 · 첫 체결 뒤',
    pnlAfterFirstCheck: '손익 · 첫 확인 뒤',
    baseline: (pct: string) => `손대지 않았을 때 ${pct}`,
    up: '▲',
    down: '▼',
  },

  /** 기준 시트: 한국 [10/7] 종가 · 미국 [10/6] 종가(ET) · 환율 [1,382.4]원 [16:00]. */
  basisSheet: {
    kr: (date: string) => `한국 ${date} 종가`,
    us: (date: string) => `미국 ${date} 종가(ET)`,
    fx: (rate: string, time: string) => `환율 ${rate} ${time}`,
    coin: (time: string) => `코인 ${time}`,
  },

  /** 설명 시트 of '손대지 않았을 때'. */
  baselineSheet: {
    title: '손대지 않았을 때',
    lines: [
      '시작일에 두 ETF를 반반 사서 그대로 둔 경우예요',
      '입출금은 같은 날 같은 금액으로 넣고 빼요',
    ],
  },

  trend: {
    title: '자산 변동',
    periods: { '1m': '1개월', '3m': '3개월', '1y': '1년', all: '전체' },
    periodGroup: '기간',
    amount: '금액',
    rate: '수익률',
    modeGroup: '금액 | 수익률',
    emptyBeforeCheck: '첫 확인 뒤 그래프가 그려져요',
    emptyBeforeFill: '첫 체결 뒤 그래프가 그려져요',
    emptyFirstDay: '그래프는 둘째 날부터',
    retColumn: '수익률',
  },

  /** 변동 분해 시트 (가로 폭포 막대). */
  breakdown: {
    title: '변동 분해',
    range: (from: string, to: string) => `${from}~${to}`,
    /** NEW — one account: money the conversions moved in or out, and its own market move. */
    transfer: '환전',
    market: '시세',
  },

  /**
   * NEW — 계좌별 보기 (the owner, 2026-10-12): '전체 · 한국 ₩ · 미국 $'. 전체 is the ledger in won;
   * each account is shown in its own money.
   */
  accounts: {
    switchLabel: '계좌',
    tabs: { all: '전체', kr: '한국 ₩', us: '미국 $' },
    name: { kr: '한국 계좌', us: '미국 계좌' },
    /** Hero label of one account: '한국 계좌 · 7/1부터'. */
    since: (name: string, date: string) => `${name} · ${date}부터`,
    fxEffect: '환율 효과',
    /** The tile of an account no money reached yet. */
    emptyShort: '비어 있음',
    /** In place of the graph and the rows: '미국 계좌는 비어 있어요'. */
    empty: (name: string) => `${name}는 비어 있어요`,
    /** 미국 계좌 gets its dollars only by conversion. */
    fillsBy: '환전하면 채워져요',
    /** Group head inside one account: '계좌의 81.4%'. */
    share: (pct: string) => `계좌의 ${pct}`,
    /** The dashed line of one account: money in by that day (start, deposits, conversions). */
    netIn: '들어온 돈',
    /** Under the legend of one account's line: why 들어온 돈 steps on a conversion day. */
    netInNote: '들어온 돈은 환전하면 두 계좌 사이로 옮겨가요',
    split: {
      title: '손익 나눠 보기',
      total: '전체 손익',
      /** '−$149.95 × 1,382.4원' */
      converted: (usd: string, rate: string) => `${usd} × ${rate}`,
      fxNote: '달러로 바꾼 돈이 지금 환율로 늘거나 준 몫이에요',
    },
  },

  /** ⓘ 표식 범례 시트 (시작 · 리밸런싱 · 일부 실패 · 진행 중 · 배당 · 입금 · 출금 · 실전 켬/끔). */
  legend: {
    title: '표식 범례',
    start: '시작',
    rebalance: '리밸런싱',
    partialFail: '일부 실패',
    inProgress: '진행 중',
    dividend: '배당',
    deposit: '입금',
    withdraw: '출금',
    live: '실전 켬/끔',
  },

  /** A grouped '[n]' marker opens the 사건 목록. */
  eventList: '사건 목록',

  plan: {
    title: '계획',
    link: '계획 보기',
    others: (count: number, status: string) => `외 ${String(count)}개 규칙 · ${status}`,
    beforeFirstCheck: '첫 확인 전',
  },

  composition: {
    title: '구성',
    groupLabel: '묶어 보기',
    groupBy: { instrument: '종목', kind: '종류', country: '나라', currency: '통화', rule: '규칙' },
    cash: '현금',
    share: (pct: string) => `자산의 ${pct}`,
    shareTarget: (pct: string, target: string) => `자산의 ${pct} · 목표 ${target}`,
    kinds: { etf: 'ETF', stock: '주식', coin: '코인' },
    currencies: { KRW: '원화', USD: '달러' },
    cashName: { KRW: '원화 현금', USD: '달러 현금' },
    withdrawCash: '원화 현금 · 출금 대기',
    cashSymbol: { KRW: '₩', USD: '$' },
    chip: {
      buyWait: (name: string, qty: number) => `매수 대기 · ${name} ${String(qty)}주`,
      /** 출시 첫날: no other dollar holding, so the name is left out ('매수 대기 · 54주'). */
      buyWaitShort: (qty: number) => `매수 대기 · ${String(qty)}주`,
      subShare: '1주 미만 대기',
      withdrawWait: (until: string) => `출금 대기 · ${until}까지`,
      firstBuy: '첫 확인 때 매수',
      buyFrom: (time: string) => `${time}부터 매수`,
    },
    /** 1440 second line / 390 expanded line: '115주 · 평균 32,005원'. */
    detail: (qty: string, avg: string) => `${qty} · 평균 ${avg}`,
    shares: (qty: number) => `${String(qty)}주`,
    coinQty: (qty: string, ticker: string) => `${qty} ${ticker}`,
    pendingNote: (amount: string, until: string) =>
      `빗금 = 출금 대기 원화 ${amount} · ${until}까지`,
    targetNote: (parts: string) => `점선 = 목표 비중 · ${parts}`,
    targetPart: (name: string, pct: string) => `${name} ${pct}`,
    outsideRules: (count: number, amount: string) =>
      `규칙 밖 ${String(count)}개 ${amount} · 손익 제외`,
  },
} as const;
