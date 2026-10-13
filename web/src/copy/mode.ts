// SCR-MODE 모의투자·실전. Sources: 기획.md §5 SCR-MODE (lines 729–798), Figma 1:64094 · 1:64317 ·
// 1:64451 · 1:64669 · 1:64799 · 1:64956 · 1:65110 · 1:65140, 예시-값표 §1.6 · §2.2 · §3,
// 인계.md (불일치 12: '30일부터' → '30거래일'). Strings marked NEW are not in the spec or Figma;
// they follow its pattern.

export const modeCopy = {
  /** NEW — accessible name of the two-cell segment. */
  segment: '지금 모드',
  line: {
    paper: '모의투자 · 실제 돈은 안 움직여요',
    live: '실전 · 규칙이 내는 주문이 실계좌로 나가요',
    paperAfterLive: '모의투자 · 실계좌 주문은 멈췄어요',
  },
  liveSince: (date: string, days: number) => `실전 ${date}부터 · ${String(days)}일째`,
  liveOff: (from: string, to: string, time: string) => `실전 ${from}~${to} · ${time}에 끔`,

  twoLedgers: {
    title: '두 장부',
    since: (date: string) => `${date}부터`,
    live: (ret: string) => `실전 ${ret}`,
    paper: (ret: string) => `모의투자 ${ret}`,
    baseline: (ret: string) => `손대지 않았을 때 ${ret}`,
    amount: '금액',
    ret: '수익률',
    /** NEW — accessible names. */
    unit: '그래프 단위',
    chart: (live: string, paper: string, baseline: string) =>
      `두 장부 그래프 · 실전 ${live} · 모의투자 ${paper} · 손대지 않았을 때 ${baseline}`,
    columns: { live: '실전', paper: '모의투자', baseline: '손대지 않았을 때' },
    breakdown: (since: string, at: string) => `차이 분해 · ${since}부터 · ${at}`,
    fills: '체결가',
    fees: '실제 수수료',
    other: '기타 · 1주 단위·시작 시점',
    total: '합',
    liveHistory: '실전 기록',
    paperHistory: '모의투자 기록',
  },

  performance: {
    title: '모의투자 성적',
    since: (date: string) => `${date}부터`,
    ops: '작동',
    times: (n: number) => `${String(n)}회`,
    items: (n: number) => `${String(n)}건`,
    checks: '확인',
    rebalances: '리밸런싱',
    failures: '실패',
    fills: '모의 체결',
    ret: '수익률',
    baseline: (ret: string) => `손대지 않았을 때 ${ret}`,
    note: '수수료 반영 · 세금 미포함',
    /** 인계 불일치 12: the drawn '30일부터' reads '30거래일부터'. */
    short: '기간 짧음 · 30거래일부터 수익률',
    shortNote: (checks: number) => `확인 ${String(checks)}회 · 수익률은 30거래일이 지나면 보여요`,
    /** Spec empty state: '아직 모의투자 기록 없음 · 첫 확인 [날짜 시각]'. */
    empty: (at: string) => `아직 모의투자 기록 없음 · 첫 확인 ${at}`,
    /** NEW — empty state when the first check time is not known. */
    emptyNoTime: '아직 모의투자 기록 없음',
    history: '모의투자 기록',
    /** NEW — accessible word for the ▲/▼ mark. */
    up: '오름',
    down: '내림',
  },

  preflight: {
    title: '켜기 전 점검',
    healthOk: '작동 정상',
    health: '작동',
    lastCheck: (at: string) => `마지막 확인 ${at}`,
    /** '점검 1 · 미국 시세 낡음'. */
    healthCause: (n: number, cause: string) => `점검 ${String(n)} · ${cause}`,
    staleCause: (source: string) => `${source} 낡음`,
    tossLink: '토스 연결',
    tossLinkLine: (date: string, days: number) => `만료 ${date} · ${String(days)}일 남음`,
    /** NEW (3단계) — no expiry known: '계좌 끝 8901 · 16:05 확인'. */
    tossLinkOk: (account: string, time: string) => `계좌 끝 ${account} · ${time} 확인`,
    /** NEW (3단계) — ✕: the cause and what to do ('주문 열쇠 꺼짐 · Claude에게 서버 cron 줄 수정 요청'). */
    tossLinkCause: (cause: string, action: string) => `${cause} · ${action}`,
    freshness: '자료 최신',
    freshLine: (balance: string, price: string, fx: string) =>
      `잔고 ${balance} · 현재가 ${price} · 환율 ${fx}`,
    staleLine: (source: string, date: string) => `${source} ${date} 기준`,
    sameCause: '위 점검과 같은 원인',
    push: '알림 받을 기기',
    pushLine: (n: number, at: string) => `${String(n)}대 · 마지막 전달 ${at}`,
    /** NEW — 0 devices: warning, does not block. */
    pushNone: '0대 · 알림을 받을 기기가 없어요',
    /** NEW — generic ✕ line when the facts carry no cause. */
    blocked: '해결이 필요해요',
  },

  preview: {
    title: '첫 주문 미리보기',
    account: '실계좌',
    now: (items: string) => `지금 · ${items}`,
    krwCash: (amount: string) => `원화 현금 ${amount}`,
    usdCash: (amount: string) => `달러 현금 ${amount}`,
    target: '목표 · 규칙대로',
    /** NEW — accessible names of the two bars. */
    nowBar: (items: string) => `지금 구성 · ${items}`,
    targetBar: (items: string) => `목표 구성 · ${items}`,
    // The live ledger never converts (D47): no 환전 leg; FxSuggestionLines says what to convert.
    stage: {
      sell: (n: number) => `매도 · ${String(n)}건`,
      buy: (n: number) => `매수 · ${String(n)}건`,
    },
    expected: (at: string) => `${at} 예상`,
    /** '한국 09:05 · 미국 22:30'. */
    marketTime: (market: string, time: string) => `${market} ${time}`,
    /** '한국 · KOSPI200 ETF 110주 · 삼성전자 14주'. */
    marketLine: (market: string, orders: string) => `${market} · ${orders}`,
    shares: (name: string, qty: string) => `${name} ${qty}주`,
    approx: (amount: string) => `약 ${amount}`,
    basisBalance: (time: string) => `잔고 ${time}`,
    basisPrice: (time: string) => `현재가 ${time}`,
    basisFx: (rate: string, time: string) => `환율 ${rate} ${time}`,
    outside: (name: string, qty: string, krw: string) =>
      `${name} ${qty} · 약 ${krw} · 토스 밖 계좌라 이 미리보기에 없어요`,
    notComputable: (at: string) => `첫 주문 계산 안 됨 · ${at} 조회`,
    /** '미국 시세가 다시 들어오면 자동으로 다시 계산해요' (subject particle added by the screen). */
    recomputeWhen: (subject: string) => `${subject} 다시 들어오면 자동으로 다시 계산해요`,
    /** NEW — the subject when the stale source is not named. */
    quotes: '시세',
    /** NEW — cause 'other'. */
    recomputeLater: '계산할 수 있게 되면 자동으로 다시 계산해요',
    /** Spec: '[시각] 다시 계산 · 금액 바뀜'. */
    changed: (at: string) => `${at} 다시 계산 · 금액 바뀜`,
  },

  turnOn: {
    title: '실전으로 켜기',
    points: [
      '실계좌로 주문이 나가요',
      '켜 둔 동안 주문마다 따로 묻지 않아요',
      '돈을 뺄 때는 토스에서 매도 · 결제일 + 2영업일 안에 출금',
    ],
    confirm: '내용을 확인했고 실전으로 켤게요',
    pin: 'PIN 6자리',
    button: '실전 켜기',
    busy: '바꾸는 중',
    busyNote: '실계좌 잔고 확인 중 · 다시 누를 수 없어요',
    /** '점검 1개(미국 시세) 해결 뒤 켤 수 있어요'. */
    blockedChecks: (n: number, causes: string) =>
      `점검 ${String(n)}개(${causes}) 해결 뒤 켤 수 있어요`,
    /** NEW — checks fail but name no cause. */
    blockedChecksCount: (n: number) => `점검 ${String(n)}개 해결 뒤 켤 수 있어요`,
    /** NEW — no preview to approve. */
    blockedPreview: '첫 주문을 계산한 뒤 켤 수 있어요',
    /** NEW — phase 1: the live executor is not connected (409 live-not-available). */
    blockedNotAvailable: '토스 주문 연결 뒤 켤 수 있어요',
    /** NEW (3단계) — an order of the last live period is still being cancelled. */
    blockedCancelPending: '지난 실전 주문의 취소가 끝나면 켤 수 있어요',
    /** Spec: '켜지 않았어요 · [이유]'. */
    failed: (reason: string) => `켜지 않았어요 · ${reason}`,
    // NEW: notAvailable · checks · preview · inProgress · pinFormat ('서버 오류' · '연결 안 됨' are
    // the spec's words).
    reasons: {
      notAvailable: '토스 주문 연결 전',
      checks: '점검 미해결',
      preview: '미리보기 없음',
      inProgress: '이미 바꾸는 중',
      server: '서버 오류',
      network: '연결 안 됨',
      pinFormat: 'PIN 6자리 숫자',
      /** NEW (3단계) */
      cancelPending: '취소 중인 주문 있음',
    },
  },

  turnOff: {
    button: '실전 끄기',
    note: '끄면 모의투자로 돌아가요 · 보유 종목은 그대로',
    title: '실전을 끌까요?',
    cancelOrders: '취소될 주문',
    /** NEW */
    noOrders: '취소될 주문 없음',
    /** '매수 · 미국 · 22:30 대기'. */
    orderHead: (side: string, market: string, time: string) => `${side} · ${market} · ${time} 대기`,
    /** 'S&P 500 ETF 2주 · 약 $124.80'. */
    orderBody: (name: string, qty: string, amount: string) => `${name} ${qty}주 · 약 ${amount}`,
    /** '달러 현금 $125.67은 계좌에 남아요' (particle chosen by the screen). */
    cashStays: (label: string, amountWithParticle: string) =>
      `${label} ${amountWithParticle} 계좌에 남아요`,
    usd: '달러 현금',
    krw: '원화 현금',
    holdingsStay: '보유 종목은 그대로',
    paperContinues: '모의투자는 계속',
    cancel: '취소',
    confirm: '끄기',
    busy: '바꾸는 중',
    /** NEW */
    failed: '끄지 못했어요 · 다시 시도',
  },

  cancelFailed: {
    title: '취소 안 된 주문 · 토스 앱에서 확인',
    /** '매수·미국 S&P 500 ETF 2주 · 약 $124.80'. */
    order: (side: string, market: string, name: string, qty: string, amount: string) =>
      `${side}·${market} ${name} ${qty}주 · 약 ${amount}`,
    waiting: (time: string) => `${time} 대기`,
    warn: (time: string) => `그대로 두면 ${time}에 체결될 수 있어요`,
    retry: '취소 다시 시도',
    /** NEW */
    retrying: '다시 시도 중',
    /** NEW */
    retryFailed: '취소하지 못했어요 · 토스 앱에서 확인',
    stateLabel: '취소 안 됨',
  },

  /** NEW (3단계) — cancels asked of Toss that the next check (5분 안) carries out. */
  cancelPending: {
    title: '취소 요청한 주문',
    note: '다음 확인 때 토스에서 취소해요 · 5분 안',
    stateLabel: '취소 요청',
  },

  /** Particles the screen picks by the last sound: '$125.67은' · '시세는' · '미국 시세가' · '환율이'. */
  particles: {
    topicAfterConsonant: '은',
    topicAfterVowel: '는',
    subjectAfterConsonant: '이',
    subjectAfterVowel: '가',
  },

  /** NEW */
  error: '모드를 못 불러왔어요',
} as const;
