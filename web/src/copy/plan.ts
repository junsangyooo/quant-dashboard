// SCR-PLAN copy, also used by the 계획 card of SCR-HOME. Sources: 기획.md §5 SCR-PLAN / SCR-HOME,
// the Figma 디자인 SCR-PLAN frames, 화면-맞춤.md ② (AI rule card, Figma 탐색 17:7108).
// Labels are short nouns; sentences use 해요체. Numbers arrive already formatted.

export const planCopy = {
  title: '계획',
  /** First load failed with nothing to show (pattern of copy.state.errors). */
  errors: { load: '계획을 못 불러왔어요' },
  ruleShares: '규칙별 자산 비중',
  exampleRule: (name: string) => `[예시] ${name}`,

  /** '자산의 81.1% · 목표 80%' — the share and target of a rule head. */
  share: {
    of: '자산의',
    target: (pct: string) => `목표 ${pct}`,
    targetAfter: (pct: string) => `· 목표 ${pct}`,
  },

  gauge: {
    mostDeviated: '가장 많이 벗어난 종목',
    toRebalance: (pp: string) => `리밸런싱까지 ${pp}`,
    closestToSell: '팔 조건에 가장 가까운 종목',
    toSell: (metric: string, margin: string) => `팔 조건까지 ${metric} ${margin}`,
    /** Accessible summary of a hollow gauge. */
    empty: '바늘 없음',
    /**
     * NEW (D47) — the live ledger's gauge: its won and dollars against the targets. The same
     * band is where a conversion is suggested; nothing rebalances between the currencies.
     */
    mixHead: '원화 · 달러 비율',
    /** NEW (D47) — '한국 76.9 : 미국 23.1'. */
    mix: (kr: string, us: string) => `한국 ${kr} : 미국 ${us}`,
    /** NEW (D47) — '환전 제안까지 1.5%p'. */
    toSuggest: (pp: string) => `환전 제안까지 ${pp}`,
  },

  row: {
    weight: (weight: string, target: string) => `${weight} · 목표 ${target}`,
    progress: (pct: string, metric: string) => `${pct} · ${metric}`,
    margin: (text: string) => `여유 ${text}`,
    dash: '—',
  },

  /** '규칙 안 비중 · 원화 기준 · 매수 대기 달러 포함 · 환율 1,382.4원 16:00'. */
  basis: {
    head: '규칙 안 비중',
    krw: '원화 기준',
    pendingBuy: '매수 대기 달러 포함',
    withdrawExcluded: '출금 대기 현금 제외',
    fx: (rate: string, time: string) => `환율 ${rate} ${time}`,
    stale: (market: string, date: string) => `${market} 시세 ${date} 기준이라 계산 안 함`,
    sellCondition: '팔 조건까지 = 고른 날 지표 → 팔 조건',
    metricTable: (date: string) => `지표 표 ${date}`,
  },

  /** Next action after a status chip ('오늘 22:30 미국 매수 2주'). */
  next: {
    today: '오늘',
    order: (when: string, market: string, side: string, qty: number) =>
      `${when} ${market} ${side} ${String(qty)}주`,
    firstCheck: (when: string) => `첫 확인 ${when} · 목표대로 매수`,
    firstOrder: (when: string) => `${when} 첫 주문`,
    firstOrderDetail: (market: string, side: string, count: number) =>
      `${market} ${side} ${String(count)}건`,
    retry: (when: string, market: string, side: string) => `${when} ${market} ${side} 다시 시도`,
    todo: '직접 할 일 · 토스 앱에서 주문 확인',
    holiday: (markets: string) => `${markets} 휴장 · 거래 없음`,
    quoteWait: (market: string, date: string) => `${market} 시세 ${date} 기준`,
    fxQuoteWait: (date: string) => `환율 ${date} 기준`,
    ordersZero: '주문 0건',
    nextCheck: (when: string) => `다음 확인 ${when}`,
    review: (date: string) => `점검 ${date}`,
  },

  /** Stage cards and the home stage row (매도 → 환전 → 매수). */
  stage: {
    name: { sell: '매도', fx: '환전', buy: '매수' },
    cardName: { sell: '매도', fx: '환전 원→달러', buy: '매수' },
    fill: { paper: '모의 체결', live: '실제 체결' },
    retryAt: (when: string) => `다시 ${when}`,
    todo: '직접 할 일',
    state: { done: '체결', pending: '대기', failed: '실패' },
    orderState: { filled: '체결', pending: '대기', failed: '실패' },
  },

  order: {
    trade: (name: string, side: string, qty: string, amount: string) =>
      `${name} ${side} ${qty} · ${amount}`,
    failedTrade: (name: string, side: string, qty: string, reason: string) =>
      `${name} ${side} ${qty} · ${reason}`,
    shares: (qty: number) => `${String(qty)}주`,
    approx: (amount: string) => `약 ${amount}`,
    fx: (krw: string, usd: string, rate: string) => `${krw} → ${usd} · ${rate}`,
    reason: {
      'no-quote': '시세 응답 없음',
      'broker-rejected': '토스 주문 거부',
      'cancel-failed': '취소 안 됨',
      other: '실패',
    },
  },

  schedule: {
    title: '예정',
    now: (status: string) => `지금 · ${status}`,
    ordersZero: '주문 0건',
    todo: '직접 할 일',
    nextCheck: '다음 확인',
    holiday: (markets: string) => `${markets} 휴장 · 거래 없음`,
    retry: (market: string, side: string) => `${market} ${side} 다시 시도`,
    krwCash: '원화 현금',
    subShare: '1주 미만 대기',
    newCash: (amount: string) => `새 현금 ${amount} · 다음 확인에 목표대로`,
    firstCheck: (when: string) => `첫 확인 ${when} · 목표대로 매수`,
    monthlyReview: '다음 월 점검',
    discovery: '다음 발굴',
    earnings: (name: string) => `${name} 실적 발표`,
    rulesLink: '규칙 그림 보기',
  },

  drift: {
    title: '벗어남 흐름',
    withPeriod: (period: string) => `벗어남 흐름 · ${period}`,
    /** NEW (D47) — the live ledger's line: how far its won and dollars were from the targets. */
    mixTitle: '원화 · 달러 비율 흐름',
    mixWithPeriod: (period: string) => `원화 · 달러 비율 흐름 · ${period}`,
    since: (date: string) => `${date}부터`,
    secondDay: '벗어남 흐름은 둘째 날부터',
    periods: { '3m': '3개월', '1y': '1년', all: '전체' },
    periodGroup: '흐름 기간',
    vsIndex: (since: string) => `지수 대비 · ${since}부터 (%p)`,
    index: '지수',
  },
} as const;
