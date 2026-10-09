// SCR-DAY 그날 copy. Sources: 기획.md §5 SCR-DAY (sections, states, 완료 조건), the Figma 디자인
// frames 1:59915 · 1:60076 · 1:60239, 예시-값표 §1.4 · §3 and 화면-맞춤.md §3 (AI 판단 사건 카드:
// '무엇이 걸렸나, 입력 요약, 판정, 모델, 토큰, 시각'). The AI card has no drawing; its words come
// from the Figma 탐색 lanes (유지 · 약화 · 반증, Haiku · Sonnet · Opus, '두 번 다 …', 토큰).

export const dayCopy = {
  prev: (date: string) => `이전 ${date}`,
  next: (date: string) => `다음 ${date}`,
  /** Accessible names of ‹ › (Figma layer '버튼 이전 사건 7/1'). */
  prevButton: (date: string) => `이전 사건 ${date}`,
  nextButton: (date: string) => `다음 사건 ${date}`,
  noPrev: '이전 사건 없음',
  noNext: '다음 사건 없음',

  total: (ledger: string) => `그날 자산 · ${ledger}`,
  vsPrevDay: '전날 대비',
  noChange: '—',

  weights: {
    title: '전후 비중',
    note: '규칙 안 · 원화 기준',
    before: '전',
    after: '후',
    target: (target: string, band: string) => `목표 ${target} · ±${band}`,
    targets: (targets: string, band: string) => `목표 ${targets} · ±${band}`,
    bar: (when: string, parts: string) => `${when} ${parts}`,
  },

  stage: {
    head: (side: string, market: string) => `${side} · ${market}`,
    fxKrwToUsd: '환전 · 원→달러',
    fxUsdToKrw: '환전 · 달러→원',
    shares: (name: string, qty: string) => `${name} ${qty}주`,
    units: (name: string, qty: string) => `${name} ${qty}`,
    approx: (value: string) => `약 ${value}`,
    fee: (value: string) => `수수료 ${value}`,
    rate: (value: string) => `환율 ${value}`,
    retry: (at: string) => `다시 ${at}`,
    retried: (date: string) => `${date} 다시 · 체결`,
    todo: '직접 할 일',
    status: { filled: '체결', pending: '대기', failed: '실패', done: '완료' },
  },

  feesTotal: (krw: string) => `수수료 합계 ${krw}`,
  feesNote: '수수료 반영 · 세금 미포함',
  /** Link to 계획 '지금' while a rebalance is still running (기획 §5 SCR-DAY 행동). */
  toPlan: '진행 중 단계 보기',

  event: {
    start: '시작',
    deposit: '입금',
    withdrawal: '출금',
    dividend: '배당',
    liveOn: '실전 켬',
    liveOff: '실전 끔',
  },

  check: {
    title: (time: string) => `그날 확인 · ${time}`,
    titleNoRun: '그날 확인',
    weekend: '주말 · 확인 없음',
    chip: {
      rebalance: '리밸런싱',
      inRange: '목표 범위 안',
      partialFailed: '일부 실패',
      failed: '실패',
      holiday: (markets: string) => `${markets} 휴장 · 거래 없음`,
      bothMarkets: '두 시장',
      quoteWait: '시세 대기',
      inProgress: '리밸런싱 중',
      withdrawWait: '출금 대기',
      noRun: '실행 없음',
    },
    deviation: (pp: string) => `${pp} 벗어남`,
    over: (pp: string) => `${pp} 넘음 → 리밸런싱`,
    onlyOpen: (market: string) => `${market}만 열린 날 · 확인은 돌았고 주문 0건`,
    position: (rule: string, instrument: string, weight: string, toThreshold: string) =>
      `${rule} ${instrument} ${weight} · 리밸런싱까지 ${toThreshold}`,
    quoteWait: '시세 대기 · 주문 0건',
    withdrawWait: '출금 대기 · 리밸런싱 쉼 · 주문 0건',
    failed: '주문 없음',
    band: (before: string, after: string, band: string) =>
      `전 ${before} → 후 ${after} · 목표 ±${band}`,
    pointBefore: (weight: string) => `전 ${weight}`,
    pointAfter: (weight: string) => `후 ${weight}`,
  },

  basis: (parts: string) => `기준 ${parts}`,
  basisKr: (date: string) => `한국 ${date} 종가`,
  basisUs: (date: string) => `미국 ${date} 종가(ET)`,
  basisFx: (rate: string, time: string) => `환율 ${rate} ${time}`,

  /** AI 판단 사건 카드 (CONTRACT AiJudgment; no Figma drawing, node-card language). */
  ai: {
    judgment: '판단',
    input: '입력',
    ai: 'AI',
    output: '출력',
    trigger: {
      shock: '급락',
      filing: '공시',
      condition: '팔 조건',
      monthly: '월 점검',
      discovery: '발굴',
      'buy-price': '살 값',
    },
    model: { haiku: 'Haiku', sonnet: 'Sonnet', opus: 'Opus' },
    verdict: {
      hold: '유지',
      weaken: '약화',
      invalidated: '반증',
      buy: '매수',
      skip: '사지 않음',
    },
    /** The two answers of a twice-asked judgment; 'switch' · 'keep' (바꾸기 확인) are NEW. */
    vote: {
      hold: '유지',
      weaken: '약화',
      invalidated: '반증',
      switch: '바꾸기',
      keep: '그대로',
    },
    /**
     * NEW — one phrase per JudgmentItem (CONTRACT AiJudgment input · output); the 입력 and 출력
     * lines join them with ' · ' in the server's order, e.g. '셀트리온 · 10/2 지수 대비 −8.1% ·
     * 최근 공시 2건'. An instrument item is its name.
     */
    items: {
      sold: (name: string) => `팔 종목 ${name}`,
      bought: (name: string) => `살 종목 ${name}`,
      shock: (date: string, pct: string) => `${date} 지수 대비 ${pct}`,
      condition: (n: number) => `반증 조건 ${String(n)}번`,
      filing: (date: string) => `${date} 공시`,
      review: (verdict: string) => `월 점검 ${verdict}`,
      reviewMonths: (verdict: string, months: number) => `월 점검 ${verdict} ${String(months)}달째`,
      month: (month: number) => `${String(month)}월`,
      cost: (pct: string) => `바꾸기 비용 ${pct}`,
      filings: (n: number) => `최근 공시 ${String(n)}건`,
      news: (n: number) => `뉴스 ${String(n)}건`,
      picks: (n: number) => `보유 ${String(n)}종목`,
      held: (n: number) => `보유 ${String(n)}종목`,
      candidates: (n: number) => `후보 ${String(n)}종목`,
      checks: (n: number) => `살 조건 ${String(n)}개 충족`,
      hold: (n: number) => `유지 ${String(n)}`,
      weaken: (n: number) => `약화 ${String(n)}`,
      invalidated: (n: number) => `반증 ${String(n)}`,
      rewritten: (n: number) => `팔 조건 고침 ${String(n)}`,
      'new-picks': (n: number) => `새 종목 ${String(n)}`,
      expired: (n: number) => `만료 후보 ${String(n)}`,
      'slot-full': '자리 없음 → 바꾸기 확인',
    },
    action: {
      none: '주문 0건',
      sell: '매도',
      buy: '매수',
      switch: '매도 · 매수',
    },
    twice: (verdict: string) => `두 번 다 '${verdict}'`,
    votes: (a: string, b: string) => `'${a}' · '${b}'`,
    tokensMan: (n: number) => `약 ${String(n)}만 토큰`,
    tokensCheon: (n: number) => `약 ${String(n)}천 토큰`,
    tokens: (n: string) => `${n} 토큰`,
  },
} as const;
