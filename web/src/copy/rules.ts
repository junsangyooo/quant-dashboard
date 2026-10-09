// SCR-RULES 규칙 copy. Sources: 기획.md §5 SCR-RULES (sections, states, 완료 조건), the Figma
// 디자인 frames 1:60971 · 1:61226 · 1:61661 · 1:61916 · 1:62197 and the 탐색 lanes of '3년 발굴'
// (17:5855 · 17:6432 · 17:7193 · 17:7808, 화면-맞춤.md §5–6: '흐름' 칩).

export const rulesCopy = {
  count: (n: number) => `규칙 ${String(n)}개`,
  viewOnly: '보기 전용',
  shareOf: '자산의',
  target: (pct: string) => `· 목표 ${pct}`,
  planLink: '계획에서 지금 위치 보기',

  tiles: {
    what: '무엇 · 비중',
    when: '언제 · 시작',
    condition: '조건',
    action: '행동',
    measured: '과거 1년 수익 · 측정',
    now: '지금 · 결과',
    ratio: (parts: readonly string[]) => parts.join(' : '),
    krwBasis: '원화 기준',
    etfCount: (n: number) => `ETF ${String(n)}개`,
    instrumentCount: (n: number) => `종목 ${String(n)}개`,
    weekdays: ['월', '화', '수', '목', '금', '토', '일'] as const,
    hour0: '0시',
    hour24: '24시',
    daily: (time: string) => `매일 ${time}`,
    kstWeekdays: '한국 시간 · 평일',
    minus: (pp: string) => `−${pp}`,
    plus: (pp: string) => `+${pp}`,
    targetMark: '목표',
    over: (pp: string) => `±${pp} 넘으면`,
    targetBasis: (pct: string) => `목표 ${pct} 기준`,
    stages: { sell: '매도', fx: '환전', buy: '매수' },
    rebalanceOrder: '리밸런싱 주문',
    toTarget: '목표 비중까지',
    measuredSub: (period: string, afterTax: boolean) =>
      afterTax ? `중간값 · 세후 · ${period}` : `중간값 · ${period}`,
    measuredRows: {
      source: '출처',
      period: '기간',
      median: '중간값',
      badYear: '나쁜 해',
      worst: '최악',
      afterTax: '세후',
    },
    nextCheck: (at: string) => `다음 확인 ${at}`,
    noStage: '—',
    conditionLabel: (now: string, check: string) => `지금 ${now} · 확인 때 ${check}`,
  },

  flow: {
    lanes: '흐름',
    fields: { input: '입력', ai: 'AI', output: '출력' },
    kinds: { etf: 'ETF', stock: '주식', coin: '코인' },
    lane: {
      daily: (time: string) => `매일 ${time}`,
      earnings: '실적 공시',
      monthly: '매달 1일',
      quarterly: '4·6·9·12월 1일',
    },
    legend: {
      taken: '이번에 지난 길',
      notTaken: '안 지난 갈래',
      exception: '예외 갈래',
    },
    edge: {
      yes: '예',
      no: '아니오',
      'no-keep': '아니오 · 그대로',
      'no-wait': '아니오 · 대기',
    },
    /** Screen-reader line under a card: where its lines go ('예 → 행동'). */
    goesTo: (label: string | null, kind: string) => (label ? `${label} → ${kind}` : `→ ${kind}`),
    canvas: (name: string) => `${name} 흐름`,
  },

  now: {
    check: (time: string) => `확인 ${time}`,
    lastJudgment: (at: string) => `마지막 판단 ${at}`,
    month: '이번 달',
    last: (at: string) => `마지막 ${at}`,
    range: (from: string, to: string) => `${from}~${to}`,
    weightsPnl: '규칙 안 비중 · 손익',
    next: (at: string) => `다음 ${at}`,
    inHours: (n: number) => `${String(n)}시간 뒤`,
    inDays: (n: number) => `${String(n)}일 뒤`,
    more: (n: number) => `외 ${String(n)}`,
    picked: (n: number) => `${String(n)}종목 고름`,
    toThreshold: (pp: string) => `리밸런싱까지 ${pp}`,
    bandScale: (pp: string) => `목표 ±${pp}`,
    filled: (date: string) => `${date} 체결`,
    retried: (date: string) => `${date} 다시 · 체결`,
    pending: (time: string) => `${time} 대기`,
    failed: '실패',
    none: '—',
    lastCheck: (at: string) => `마지막 확인 ${at}`,
    exceptionsNone: '지금 해당 없음',
    progress: { from: '고른 날', zone: '확인 구간 80%~', to: '팔 조건' },
    targets: (parts: string) => `목표 ${parts}`,
  },

  /** 예외 칩 설명 (기획 §5 SCR-RULES 행동: '휴장 → 다음 개장일 확인'). */
  exceptionHelp: {
    holiday: '휴장 → 다음 개장일 확인',
    awaitingQuote: '시세 대기 → 주문 0건',
    withdrawPending: '출금 대기 → 리밸런싱 쉼',
  },
} as const;
