// Every user-visible string lives here. Sources: 기획.md §5 (screen spec), the Figma
// 디자인 page and 예시-값표.md. Labels are short nouns; sentences use 해요체.
// The skip-link wording is not in the spec; it reuses the existing app's wording.

export const copy = {
  wordmark: 'quant',

  /** Units and weekday names used by lib/format. */
  units: {
    won: '원',
    eok: '억',
    man: '만',
    pp: '%p',
  },
  weekdaysShort: ['일', '월', '화', '수', '목', '금', '토'] as const,
  skipLink: '본문으로 건너뛰기',
  back: '뒤로',
  close: '닫기',
  settings: '설정',

  nav: {
    home: '자산',
    plan: '계획',
    history: '기록',
    rules: '규칙',
  },

  pages: {
    pin: '입장',
    home: '자산',
    plan: '계획',
    history: '기록',
    day: '그날',
    rules: '규칙',
    health: '작동',
    mode: '모의투자·실전',
    account: '설정',
  },

  mode: {
    paper: '모의투자',
    live: '실전',
  },

  headerStatus: {
    ok: (time: string) => `정상 · ${time} 확인`,
    beforeFirstCheck: '첫 확인 전',
    check: (n: number) => `점검 ${String(n)}`,
    checkFailed: '확인 실패',
    unknown: '확인 불가',
    todo: (n: number) => `직접 할 일 ${String(n)}`,
    notCancelled: (n: number) => `취소 안 됨 ${String(n)}`,
    offline: '연결 안 됨',
  },

  rebalance: {
    inRange: '목표 범위 안',
    scheduled: '리밸런싱 예정',
    inProgress: '리밸런싱 중',
    partialFail: '일부 실패',
    holiday: '휴장',
    awaitingQuote: '시세 대기',
    withdrawPending: '출금 대기',
  },

  /** AI rules reuse the seven chips with other words (화면-맞춤.md ②, CONTRACT RuleStatus). */
  ruleStatusAi: {
    hold: '유지',
    sellScheduled: '매도 예정',
    buyScheduled: '매수 예정',
    inProgress: '주문 중',
  },

  market: {
    KR: '한국',
    US: '미국',
    COIN: '코인',
    FX: '환율',
  },

  side: {
    buy: '매수',
    sell: '매도',
    fx: '환전',
  },

  /** Shared screen states (기획 §5: loading · error · offline · other device · example). */
  state: {
    example: '예시',
    retry: '다시 불러오기',
    offlineLoaded: (time: string) => `${time} 불러온 값 · 연결 안 됨`,
    modeChanged: (time: string, from: string, toWithParticle: string) =>
      `${time} 다른 기기에서 ${from} → ${toWithParticle} 바뀜`,
    /** Target mode with its particle: '모의투자로' / '실전으로'. */
    modeTo: { paper: '모의투자로', live: '실전으로' },
    errors: {
      history: '기록을 못 불러왔어요',
      day: '그날 기록을 못 불러왔어요',
      rules: '규칙을 못 불러왔어요',
      health: (time: string) => `상태를 못 불러왔어요 · ${time} 시도`,
    },
  },

  /** 이상 배너 (SCR-HOME 섹션 '이상 배너'): one fact and a move link. */
  banner: {
    stale: (market: string, date: string, days: number) =>
      `${market} 시세 ${date} 기준 · ${String(days)}거래일째 갱신 없음`,
    /** FX has no '시세' (not drawn in Figma; composed from the stale line). */
    staleFx: (date: string, days: number) =>
      `환율 ${date} 기준 · ${String(days)}거래일째 갱신 없음`,
    partialRetry: (date: string, market: string, side: string, retryAt: string) =>
      `${date} ${market} ${side} 실패 · ${retryAt} 다시 시도`,
    partialTodo: (date: string, market: string, side: string, reason: string) =>
      `${date} ${market} ${side} 실패 · ${reason} · 직접 할 일`,
    /** Why a failure became 직접 할 일. 'retry-failed' is not drawn; composed like the drawn one. */
    todoReason: { 'broker-rejected': '토스 주문 거부', 'retry-failed': '다시 시도도 실패' },
    checkFailed: (at: string, retryAt: string | null) =>
      retryAt === null ? `${at} 확인 실패` : `${at} 확인 실패 · ${retryAt} 자동 재시도`,
    cancelFailed: (market: string, side: string) =>
      `모의투자로 바뀜 · ${market} ${side} 주문 취소 안 됨`,
    pushUndelivered: (days: number) => `알림이 ${String(days)}일째 기기에 안 닿아요`,
    link: {
      health: '작동 보기',
      plan: '계획 보기',
      mode: '다시 시도',
      account: '시험 알림',
    },
  },

  exception: {
    holiday: '휴장',
    awaitingQuote: '시세 대기',
    withdrawPending: '출금 대기',
    newCash: '새 현금',
  },

  ai: {
    none: 'AI 없음',
    included: 'AI 판단 포함',
  },

  stale: '낡음',
  collapse: '접기',
  now: '지금',

  nodeKind: {
    start: '시작',
    asset: '종목',
    data: '데이터',
    ai: 'AI 판단',
    weight: '비중',
    condition: '조건',
    action: '행동',
    exception: '예외',
    result: '결과',
  },

  event: {
    rebalance: '리밸런싱',
    rebalanceInProgress: '리밸런싱 중',
    partialFail: '일부 실패',
    deposit: '입금',
    withdraw: '출금',
    dividend: '배당',
    liveOn: '실전 켬',
    liveOff: '실전 끔',
    start: '시작',
    runFail: '확인 실패',
    // AI rule events (2단계, 화면-맞춤.md 기록): no Figma markers yet.
    discovery: '발굴',
    aiBuy: '매수',
    aiSell: '매도',
    aiCheck: 'AI 확인',
    monthlyReview: '월 점검',
  },

  calendar: {
    weekdays: ['월', '화', '수', '목', '금'] as const,
    month: (m: number) => `${String(m)}월`,
    state: {
      ok: '정상 실행',
      rebalance: '리밸런싱',
      rebalanceInProgress: '리밸런싱 중',
      partialFail: '일부 실패',
      fail: '실패',
      noRun: '실행 없음',
      holiday: '두 시장 휴장',
      future: '앞으로',
      beforeRecord: '기록 전',
      oneMarketHoliday: '한쪽 휴장',
      awaitingQuote: '시세 대기',
    },
  },

  country: {
    kr: '한국',
    us: '미국',
    coin: '코인',
  },

  pin: {
    prompt: 'PIN 6자리',
    forgot: '잊었을 때',
    forgotHelp: 'PIN을 잊었다면 서버에서 다시 정해요 · Claude에게 요청',
    delete: '지우기',
  },

  chart: {
    myAssets: '내 자산',
    untouched: '손대지 않았을 때',
    tableView: '표로 보기',
    dateColumn: '날짜',
    markerLegend: '표식 범례',
    awaitingQuoteFrom: (date: string) => `${date}부터 시세 대기`,
    before: '전',
    after: '후',
  },

  waterfall: {
    start: '기간 시작',
    deposit: '입금',
    withdraw: '출금',
    market: '시세·환율',
    dividend: '배당',
    fee: '수수료',
    end: '지금',
  },
} as const;

// Sample copy for the DEV-only component gallery (/_kit). Same sources as above.
// Dates follow the no-padding rule (10/7, 10/2); the spec writes some as 10/07, 10/02.
export const kitCopy = {
  title: '컴포넌트',
  banner: '미국 시세 10/2 기준 · 2거래일째 갱신 없음',
  bannerLink: '작동 보기',
  linkButton: '규칙 보기',
  expandButton: '비교 기준 설명',
  info: '16:00 기준',
  infoExample: '예시',
  periods: ['1개월', '3개월', '1년', '전체'] as const,
  amountRate: ['금액', '수익률'] as const,
  legendPaper: '모의투자',
  signals: { ok: '제때', warn: '늦음', error: '낡음', unknown: '확인 불가' },
  ruleIndex: '지수 반반',
  ruleMomentum: '[예시] 종목 모멘텀',
  ruleIndexWeight: '80%',
  ruleMomentumWeight: '20%',
  modeStripPaper: '모의투자 · 실제 돈은 안 움직여요',
  modeStripLive: '실전 · 규칙이 내는 주문이 실계좌로 나가요',
  buttons: { cancel: '취소', primary: '실전 켜기', danger: '실전 끄기' },
  modalTitle: '실전을 끌까요?',
  modalBody: '달러 현금 $125.67은 계좌에 남아요',
  modalConfirm: '끄기',
  modalOpen: '실전 끄기',
  toggle: '이 기기에서 알림 받기',
  checkbox: '내용을 확인했고 실전으로 켤게요',
  statusLines: {
    ok: '토스 잔고 08:30 대조 일치',
    warn: '미국 시세 10/2 기준 · 2거래일째 갱신 없음',
    error: '10/7 08:30 확인 실패 · 09:30 자동 재시도',
    wait: '다음 확인 10/8(목) 08:30',
  },
  checkRows: {
    pass: { name: '작동 정상', desc: '마지막 확인 10/7 08:30' },
    blocked: { name: '작동 · 점검 1', desc: '미국 시세 낡음' },
    warn: { name: '토스 연결', desc: '만료 10/19 · 12일 남음' },
  },
  orderRows: {
    filled: { text: 'KOSPI200 ETF 5주', time: '09:05' },
    pending: { text: 'S&P 500 ETF 2주', time: '22:30' },
    failed: { text: 'S&P 500 ETF 2주', time: '22:30' },
  },
  expandRow: { title: '8/21(금) · 리밸런싱', subtitle: '2.3%p 벗어남 · 모의 체결' },
  ruleBlocks: {
    time: '매일 08:30',
    ai: 'AI 판단 · 목표 비중',
    condition: '2%p 넘게 벗어났나요?',
    hold: '그대로',
    sell: '매도',
    exchange: '환전',
    buy: '매수',
  },
  ruleCardHead: { name: '지수 반반', shareLabel: '자산의', share: '80%' },
  kinds: { etf: 'ETF', stock: '주식', coin: '코인' },
  nodes: {
    start: {
      title: '매일 08:30',
      sub: '한국 시간 · 평일',
      next: '다음 10/8 08:30',
      in: '23시간 뒤',
    },
    asset: { title: '후보군 8종목', more: '외 5', nowSuffix: '· 규칙 안 비중 · 손익' },
    data: {
      title: '30일 수익률',
      sub: '종목마다 · 어제 종가 기준',
      nowSuffix: '· 8종목 중 상위 3',
    },
    ai: {
      title: '상위 3 고르고 비중 정하기',
      rows: [
        ['입력', '8종목 · 30일 수익률'],
        ['AI', '상위 3 고르고 비중'],
        ['출력', '3종목 · 비중'],
      ],
      nowSuffix: '· 마지막 판단 10/7 08:30',
      picked: '3종목 고름',
      same: '지난번과 같은 3종목',
    },
    weight: {
      title: '42 · 40 · 18',
      sub: '규칙 안 비중',
      now: '42.0 · 39.0 · 18.9',
      target: '목표 42 · 40 · 18',
    },
    condition: {
      title: '2%p 넘게 벗어났나요?',
      sub: '목표 비중과 지금 비중 비교',
      value: 'KOSPI200 ETF +2.4%p',
      over: '0.4%p 넘음',
      band: '목표 ±2%p',
    },
    action: {
      title: '리밸런싱 주문',
      nowSuffix: '· 마지막 9/14~9/15',
      rows: [
        ['매도 1 · 삼성전자', '9/14 체결'],
        ['환전 없음 · 코인은 원화', '—'],
        ['매수 1 · BTC', '9/15 다시 · 체결'],
      ],
    },
    exception: { title: '다음 확인으로 미룸', none: '지금 해당 없음' },
    result: {
      title: '리밸런싱 상태',
      sub: '지금 상태 · 마지막 실행',
      last: '마지막 확인 10/7 08:30',
    },
  },
  assets: {
    samsung: '삼성전자',
    nvda: 'NVDA',
    btc: 'BTC',
    kospi: 'KOSPI200 ETF',
    sp500: 'S&P 500 ETF',
  },
} as const;
