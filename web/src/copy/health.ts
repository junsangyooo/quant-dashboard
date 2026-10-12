// SCR-HEALTH 작동. Sources: 기획.md §5 SCR-HEALTH (lines 681–727), Figma 1:62685 · 1:62952 ·
// 1:63248 · 1:63518 · 1:63806 (and its hidden '알림 기기' list), 예시-값표 §0 · §1.5 · §3,
// 화면-맞춤.md §3 (new sources: 공시 · AI 호출 · 지표 표). Strings marked NEW are not in the spec
// or Figma; they follow the drawn pattern. Dates come in unpadded (10/7), as everywhere.

export const healthCopy = {
  summary: {
    ok: '정상',
    check: (n: number) => `점검 ${String(n)}`,
    checkFailed: '확인 실패',
    unknown: '확인 불가',
    beforeFirst: '첫 확인 전',
    /** '자료 6개 중 할 일 1' · '자료 6개 중 낡음 1 · 할 일 1'. */
    sourcesWith: (total: number, parts: string) => `자료 ${String(total)}개 중 ${parts}`,
    stalePart: (n: number) => `낡음 ${String(n)}`,
    todoPart: (n: number) => `할 일 ${String(n)}`,
    /** NEW — no stale source and nothing to do. */
    sourcesFine: (total: number) => `자료 ${String(total)}개 모두 제때`,
    /** '10/7 08:30 · 시세 응답 없음'. */
    failedLine: (at: string, reason: string) => `${at} · ${reason}`,
    /** Spec: '첫 확인 [7/1 08:30] 예정'. */
    firstCheckLine: (at: string) => `첫 확인 ${at} 예정`,
    /** NEW — the server itself answered 'unknown'. */
    unknownLine: '자료 상태를 알 수 없어요',
    lastAndNext: (last: string, next: string) => `마지막 확인 ${last} · 다음 ${next}`,
    /** NEW — before the first check there is no 'last'. */
    nextOnly: (next: string) => `다음 확인 ${next}`,
    lastSuccessRetry: (last: string, retry: string) => `마지막 성공 ${last} · 다시 ${retry}`,
    /** NEW — failed and no retry left. */
    lastSuccess: (last: string) => `마지막 성공 ${last}`,
    lastReceived: (at: string) => `마지막으로 받은 상태 ${at}`,
    unknownChip: '상태 모름',
    todoChip: (n: number) => `할 일 ${String(n)}`,
    /** '점검 1 · 할 일 1' (1:46904). */
    checkChip: (n: number, todo: number) =>
      todo > 0 ? `점검 ${String(n)} · 할 일 ${String(todo)}` : `점검 ${String(n)}`,
    failChip: (n: number) => `실패 ${String(n)}`,
  },

  /** 할 일 카드. Two 해요체 lines + a small result line. */
  todo: {
    /** NEW — screen-reader heading of the cards. */
    title: '할 일',
    autoRetry: (at: string) => `${at} 자동 재시도`,
    manual: '직접 할 일',
    // 토스 연결 만료 예정 (1:38782)
    tossExpiringTitle: (date: string) => `토스 연결 만료 예정 · ${date}`,
    tossExpiringLines: (days: number) => [
      `${String(days)}일 뒤 토스 연결이 끝나요`,
      '그 전에 Claude에게 재연결 요청',
    ],
    // 자료 낡음 (1:46904)
    staleTitle: (source: string, date: string, days: number) =>
      `${source} ${date} 기준 · ${String(days)}거래일째`,
    /** '10/5·10/6 미국 종가를 못 받았어요' — the missing dates are joined with '·'. */
    staleMissing: (dates: string, market: string) => `${dates} ${market} 종가를 못 받았어요`,
    /** NEW — when the response does not list the missing dates. */
    staleMissingCount: (market: string, days: number) =>
      `${market} 종가 ${String(days)}거래일치를 못 받았어요`,
    /** NEW — stale exchange rate. */
    staleFxMissing: (days: number) => `환율을 ${String(days)}거래일째 못 받았어요`,
    nextAttempt: (at: string) => `다음 시도 ${at}`,
    // 확인 실패 (1:47501). The drawing says '토스 시세'; the source is not always Toss (phase 1
    // reads public quotes), so the reason word alone is used.
    checkFailedTitle: (at: string) => `${at} 확인 실패`,
    checkFailedLines: (reason: string, retry: string) => [
      `${reason} · 주문은 나가지 않았어요`,
      `${retry}에도 실패하면 알림이 가요`,
    ],
    checkFailedResult: '두 번 실패하면 직접 할 일 · 작동에서 확인',
    /** NEW — the retry failed too (manual). */
    checkFailedManualLines: (reason: string) => [
      `${reason} · 다시 시도도 실패했어요`,
      '오늘은 주문이 나가지 않아요 · Claude에게 원인 확인 요청',
    ],
    // 주문 실패 (다시 시도까지 실패, CONTRACT order-failed) — NEW, from the banner wording.
    orderFailedTitle: (date: string, market: string, side: string) =>
      `${date} ${market} ${side} 실패`,
    orderFailedLines: ['다시 시도도 실패했어요', 'Claude에게 원인 확인 요청'],
    // 토스 주문 거부 (실전, 3단계) — '직접 할 일 · 토스 앱에서 주문 확인' (예시-값표 §3); first line NEW.
    orderRejectedTitle: (date: string, market: string, side: string) =>
      `${date} ${market} ${side} · 토스 주문 거부`,
    orderRejectedLines: ['토스가 주문을 받지 않았어요', '토스 앱에서 주문 확인'],
    // 취소 안 된 주문 (SCR-MODE off-failed wording); second line NEW.
    cancelFailedTitle: '취소 안 된 주문 · 토스 앱에서 확인',
    cancelFailedLines: (time: string) => [
      `그대로 두면 ${time}에 체결될 수 있어요`,
      '모의투자·실전에서 취소 다시 시도',
    ],
    // 알림 안 닿음 (banner wording) — lines NEW.
    pushUndeliveredTitle: (days: number) => `알림이 ${String(days)}일째 기기에 안 닿아요`,
    pushUndeliveredLines: ['설정에서 시험 알림을 보내 봐요', '안 오면 이 기기 알림을 다시 켜요'],
    // AI 호출 · 공시 (2단계, 화면-맞춤 §3) — NEW.
    // AI 호출 빨강: 세 번 실패한 일감이 사람을 기다려요 (facts reason 'task-failed', count,
    // taskKind, since = 그중 가장 오래된 일감이 생긴 시각).
    aiCliTitle: (at: string) => `AI 호출 실패 · ${at}부터`,
    /** NEW — the failed tasks: '팔기 확인 2건이 세 번 실패했어요'. */
    aiTaskFailed: (task: string, n: number) => `${task} ${String(n)}건이 세 번 실패했어요`,
    aiLogin: 'Claude 구독 로그인 확인 요청',
    /** NEW — AI 일감 names (the engine's task kinds); another kind reads 'AI 일감'. */
    aiTasks: {
      'sell-confirm': '팔기 확인',
      'buy-confirm': '사기 확인',
      switch: '바꾸기 확인',
      'monthly-review': '월 점검',
      discovery: '분기 발굴',
      extract: '지표 뽑기',
    },
    aiTaskOther: 'AI 일감',
    // AI 호출 노랑: 한 달 토큰이 예산을 넘었어요, 멈추지는 않아요 (facts reason 'over-budget',
    // tokens, budget; no time).
    /** NEW */
    aiBudgetTitle: 'AI 토큰 예산 넘음',
    /** NEW */
    aiBudgetLines: (used: string, budget: string) => [
      `이번 달 ${used} · 예산 ${budget}`,
      'AI 판단은 그대로 돌아요',
    ],
    /** NEW — '324만 토큰'. */
    tokens: (n: string) => `${n} 토큰`,
    // AI 실행기의 심장 박동에서 오는 카드 (10/10 점검 뒤) — NEW.
    /** 빨강: 서버에서 Claude CLI를 못 찾음 (facts reason 'cli-missing', since?). */
    aiCliMissingTitle: 'Claude CLI 없음',
    aiCliMissingSince: (at: string) => `${at}부터 못 찾았어요`,
    aiCliMissingLines: [
      'AI 일감은 시도로 세지 않고 기다려요',
      '서버의 claude 설치와 cron 줄 확인 요청',
    ],
    /** 노랑: 호출 하나가 오래 이어짐 (facts reason 'call-running', taskKind, since). */
    aiCallRunningTitle: (task: string, at: string) => `${task} 호출이 ${at}부터 이어져요`,
    aiCallRunningLines: [
      '시간 상한은 없어서 그대로 기다려요',
      '너무 길면 서버의 claude 상태 확인 요청',
    ],
    /** 노랑: 일감이 차례를 못 받음 (facts reason 'queue-waiting', count, since, cause). */
    aiQueueTitle: (n: number) => `AI 일감 ${String(n)}건이 기다려요`,
    aiQueueSince: (at: string) => `가장 오래된 일감 ${at}`,
    aiQueueCause: {
      off: 'AI 호출이 꺼져 있어요',
      stopped: 'AI 실행기가 돌지 않아요 · cron 확인 요청',
      busy: '긴 호출 하나가 실행기를 잡고 있어요',
      'cli-missing': 'Claude CLI를 찾지 못했어요',
      deferred: '출처·키·자료를 기다려요',
    },
    /** 공시 빨강, state 'no-key': AI 실행기에 DART 키가 없음 (action 'manual'). */
    filingsNoKeyTitle: (market: string) => `${market} 공시 키 없음`,
    filingsNoKeyLines: (market: string) => [
      `${market} 공시 원문을 읽을 키가 없어요`,
      '서버 cron 줄의 키 파일 확인 요청',
    ],
    // 공시 빨강: 공시 감시가 멈춰요, 다음 확인 때 다시 (facts source, market, state, since?).
    filingsTitle: (market: string) => `${market} 공시 수집 점검 중`,
    filingsLines: (market: string) => [
      `${market} 공시 감시가 멈췄어요`,
      '점검이 끝나면 자동으로 다시 받아요',
    ],
    /** NEW — state other than maintenance (응답 없음 · 키 없음 · 실패). */
    filingsStoppedTitle: (market: string) => `${market} 공시 수집 멈춤`,
    /** NEW */
    filingsStoppedLines: (market: string) => [
      `${market} 공시 감시가 멈췄어요`,
      '다음 확인 때 다시 받아요',
    ],
    /** NEW — facts.since, when the watch last received a filing. */
    filingsSince: (at: string) => `마지막으로 받음 ${at}`,
    // PIN 실패 급증 (CONTRACT pin-failures; the name is the 알림 사건's, copy/account.ts) — NEW.
    // Red and manual from 10 wrong PINs in 24 hours until the server's unlock (facts since, count,
    // lastAt?, closed 1 = new logins closed at 30).
    pinFailuresName: 'PIN 실패 급증',
    pinFailuresTitle: (at: string) => `PIN 실패 급증 · ${at}부터`,
    pinFailuresCount: (n: number, last: string | null) =>
      last === null ? `틀린 PIN ${String(n)}회` : `틀린 PIN ${String(n)}회 · 마지막 ${last}`,
    pinFailuresClosed: '새 로그인이 닫혔어요 · 열린 기기는 그대로 써요',
    pinFailuresOpen: '새 로그인은 아직 열려 있어요',
    pinFailuresResult: 'Claude에게 서버에서 unlock 요청 · 그러면 이 카드도 사라져요',
    // 실전 연결 (3단계, autotrade/PHASE3.md 2.7) — NEW. 토스 연결: facts { cause } (lines: toss.lines).
    tossLinkTitle: (cause: string) => `토스 연결 · ${cause}`,
    // 토스 잔고 불일치: facts { reason, instrument?, ledgerQty?, brokerQty?, count?, currency? }.
    brokerMismatchTitle: '토스 잔고와 장부가 달라요',
    /** 'KOSPI200 ETF 장부 0주 · 토스 3주' (+ ' 외 1종목'). */
    brokerMismatchQty: (name: string, ledger: string, broker: string, more: number) =>
      `${name} 장부 ${ledger}주 · 토스 ${broker}주${more > 0 ? ` 외 ${String(more)}종목` : ''}`,
    brokerMismatchCash: (currency: string) => `${currency} 현금이 장부로 설명되지 않게 바뀌었어요`,
    brokerMismatchFill: (name: string) => `${name} 체결을 장부에 맞출 수 없어요`,
    brokerMismatchOther: '장부로 설명되지 않는 차이가 있어요',
    brokerMismatchAction: '토스 앱에서 확인 뒤 Claude에게 장부 맞추기 요청',
    // 결과를 모르는 주문: facts { reason: 'order-unknown', market, side }.
    orderUnknownTitle: (market: string, side: string) => `${market} ${side} 주문 결과 모름`,
    orderUnknownLines: [
      '토스에 이 주문으로 보이는 것이 둘이에요',
      '토스 앱에서 확인 뒤 Claude에게 요청',
    ],
    // 토스 앱에서 환전: facts { direction, krw, usd, rate, orderId, by? }.
    fxManualTitle: (direction: string) => `토스 앱에서 환전 · ${direction}`,
    fxDirection: { 'krw-usd': '원→달러', 'usd-krw': '달러→원' },
    /** '약 4,967,000원 → $3,568.24 · 환율 1,392.0원'. */
    fxManualAmount: (from: string, to: string, rate: string) => `${from} → ${to} · 환율 ${rate}`,
    fxManualBy: (at: string) => `${at} 미국 매수 전까지 바꿔 주세요`,
    fxManualNoBy: '토스 API는 환전을 못 해서 직접 바꿔 주세요',
    fxManualResult: '바뀐 돈이 보이면 다음 확인이 이어서 주문해요',
    /** The won side is an estimate until Toss fills it: '약 4,967,000원'. */
    fxApprox: (amount: string) => `약 ${amount}`,
    /** Small result line, by effect. */
    effect: {
      'orders-zero-live-blocked': '그동안 주문 0건 · 실전 켜기 막힘',
      'orders-and-reconcile-stop': '끝나면 실전 주문과 잔고 대조가 멈춰요',
      /** NEW — used when no kind-specific line exists. */
      'no-order-sent': '주문은 나가지 않았어요',
    },
  },

  sources: {
    title: '자료별',
    barNote: '막대 = 갱신 주기 대비 나이',
    names: {
      'kr-quotes': '한국 시세',
      'us-quotes': '미국 시세',
      fx: '환율',
      'toss-link': '토스 연결',
      'toss-balance': '토스 잔고 대조',
      'push-devices': '알림 기기',
      // 2단계 (화면-맞춤 §3: 공시 · AI 호출 · 지표 표)
      filings: '공시',
      'ai-cli': 'AI 호출',
      'metric-table': '지표 표',
    },
    state: {
      fresh: '제때',
      late: '늦음',
      stale: '낡음',
      /** 화면-맞춤 §3 ('DART가 점검 중이면 점검 중'). */
      maintenance: '점검 중',
      unknown: '확인 불가',
    },
    cadence: {
      daily: '매일',
      'per-check': '확인마다',
      '90d': '90일마다 갱신',
      /** NEW */
      event: '생길 때마다',
    },
    close: (date: string) => `${date} 종가`,
    closeEt: (date: string) => `${date} 종가(ET)`,
    received: (time: string) => `${time} 받음`,
    expires: (date: string) => `만료 ${date}`,
    daysLeft: (days: number) => `${String(days)}일 남음`,
    /** Chip of a 토스 연결 that expires soon: '만료 12일 전'. */
    expiresIn: (days: number) => `만료 ${String(days)}일 전`,
    balanceMatch: (time: string) => `${time} 일치`,
    /** NEW */
    balanceMismatch: (time: string) => `${time} 불일치`,
    devices: (n: number) => `${String(n)}대`,
    lastDelivery: (at: string) => `마지막 전달 ${at}`,
    // 2단계 rows (화면-맞춤 §3). NEW: filingsBasis · maintenanceStop.
    lastSuccess: (at: string) => `마지막 성공 ${at}`,
    filingsBasis: (date: string) => `${date} 공시까지`,
    metricBasis: (date: string) => `마지막 실적 뽑기 ${date}`,
    maintenanceStop: (market: string) => `${market} 공시 감시 멈춤`,
    /** NEW — the AI runner found no Claude CLI (extra.cli 'missing'). */
    cliMissing: 'Claude CLI 없음',
    /** NEW (3단계) — 토스 연결 row: '계좌 끝 8901 · 16:05 확인'. */
    account: (tail: string) => `계좌 끝 ${tail}`,
    checked: (time: string) => `${time} 확인`,
    noValue: '—',
    /** NEW — accessible name of the push row button. */
    devicesToggle: '알림 기기 목록',
  },

  /** 알림 기기 list (hidden layer of 1:62685: icon · name · '마지막 전달' · dot). */
  devices: {
    title: '알림 기기',
    /** The drawn header link. */
    settings: '알림 설정',
    /** Spec: shown when there is no device or a delivery broke. */
    enable: '설정에서 켜기',
    /** NEW */
    none: '알림 받는 기기가 없어요',
    /** NEW — screen-reader words of the status dot. */
    ok: '전달 정상',
    warn: '전달 끊김',
    never: '아직 전달 없음',
  },

  recent: {
    title: '최근 14일 확인',
    /** '14일 중 실패 0' · '14일 중 실패 0 · 시세 대기 2'. */
    summary: (fails: number, quoteWait: number) =>
      quoteWait > 0
        ? `14일 중 실패 ${String(fails)} · 시세 대기 ${String(quoteWait)}`
        : `14일 중 실패 ${String(fails)}`,
    /** '9/24~10/7 · 주말은 빈칸'. */
    range: (from: string, to: string) => `${from}~${to} · 주말은 빈칸`,
    /** '10/7 08:30 확인 · 리밸런싱 시작 · 42초'. */
    run: (at: string, result: string, tail: string) => `${at} 확인 · ${result} · ${tail}`,
    /** '10/7 08:30 확인 실패 · 시세 응답 없음 · 12초'. */
    runFailed: (at: string, reason: string, tail: string) =>
      `${at} 확인 실패 · ${reason} · ${tail}`,
    /** A failed day of the grid whose reason the response does not carry. */
    runFailedShort: (at: string, tail: string) => `${at} 확인 실패 · ${tail}`,
    seconds: (s: number) => `${String(s)}초`,
    /** Spec: a quote wait ends with '주문 0건' instead of the time taken. */
    noOrders: '주문 0건',
    /** A weekday without a run: '9/26(금) · 두 시장 휴장'. */
    day: (date: string, state: string) => `${date} · ${state}`,
    results: {
      rebalance: '리밸런싱 시작',
      'already-planned': '리밸런싱 시작',
      'in-range': '목표 범위 안',
      holiday: '휴장',
      'quote-wait': '시세 대기',
      'withdraw-wait': '출금 대기',
      'in-progress': '리밸런싱 중',
      'partial-failed': '일부 실패',
      /** NEW */
      running: '확인 중',
    },
    reasons: {
      'no-quote': '시세 응답 없음',
      /** NEW */
      other: '원인 확인 필요',
    },
    /** NEW — accessible names. */
    grid: '최근 14일 확인 달력',
    lastRun: '마지막 확인',
    selected: '고른 날',
  },

  /** 토스 연결이 실전 주문을 못 싣는 이유 (CONTRACT TossLinkCause) — NEW, 3단계. */
  toss: {
    cause: {
      never: '아직 확인 전',
      'env-off': '주문 열쇠 꺼짐',
      'no-key': '서버에 키 없음',
      auth: '키 거부',
      ip: '허용 IP 아님',
      account: '계좌 못 찾음',
      unreachable: '응답 없음',
      maintenance: '토스 점검 중',
      error: '토스 오류',
      old: '확인 늦음',
      conflict: '다른 프로그램과 키 겹침',
      'not-tradable': '거래 안 되는 종목',
      mismatch: '잔고 불일치',
      expired: '키 만료',
    },
    /** Two lines per cause: what happened · what to do (할 일 카드, 점검 줄은 둘째 줄만). */
    lines: {
      never: ['주문 실행기가 아직 토스를 보지 않았어요', '서버 cron 줄 확인 요청'],
      'env-off': [
        '주문 실행기에 AUTOTRADE_LIVE_ORDERS=1이 없어요',
        'Claude에게 서버 cron 줄 수정 요청',
      ],
      'no-key': ['서버 키 파일에 토스 키가 없어요', 'Claude에게 키 파일 확인 요청'],
      auth: ['토스가 서버의 키를 받지 않았어요', '토스 WTS에서 키 확인 뒤 Claude에게 교체 요청'],
      ip: ['토스가 서버 IP를 막았어요', '토스 WTS 허용 IP에 서버 주소 추가'],
      account: ['키에 묶인 계좌를 못 찾았어요', '토스 WTS에서 계좌 확인'],
      unreachable: ['토스가 응답하지 않아요', '다음 확인 때 다시 봐요'],
      maintenance: ['토스가 점검 중이에요', '끝나면 다음 확인 때 다시 봐요'],
      error: ['토스가 오류를 냈어요', '다음 확인 때 다시 봐요'],
      old: ['마지막 확인이 15분보다 오래됐어요', '다음 확인 때 다시 봐요'],
      conflict: [
        '다른 프로그램이 같은 키로 토큰을 받아요',
        'Claude에게 옛 quant cron 줄 삭제 요청',
      ],
      'not-tradable': ['규칙 종목이 지금 거래되지 않아요', '토스 앱에서 종목 상태 확인'],
      mismatch: ['토스 잔고가 장부와 달라요', '토스 잔고 대조 카드 확인'],
      expired: ['알려 준 키 만료일이 지났어요', '토스 WTS에서 새 키를 받아 Claude에게 교체 요청'],
    },
  },
} as const;
