// SCR-HISTORY 기록 copy. Sources: 기획.md §5 SCR-HISTORY (sections, states, 완료 조건), the Figma
// 디자인 frames 1:58215 · 1:58777 · 1:59344 and 인계.md '명세 정정' (장부 칩 '실전 중에 보는 중').
// Labels are short nouns; numbers and dates come in already formatted (lib/format).

export const historyCopy = {
  /** '모의투자 기록 · 2026' */
  title: (ledger: string, year: number) => `${ledger} 기록 · ${String(year)}`,
  /** 장부 칩 when ?ledger= is the other ledger: '모의투자 장부' + '· 실전 중에 보는 중'. */
  ledgerChip: (ledger: string) => `${ledger} 장부`,
  viewingWhile: (mode: string) => `· ${mode} 중에 보는 중`,
  /** Accessible name of the chip's × (back to the current mode's record). */
  closeLedger: (mode: string) => `닫기 · ${mode} 기록으로`,
  years: '연도',

  asset: {
    since: (date: string) => `자산 변동 · ${date}부터`,
    basis: (at: string) => `${at} 기준`,
    note: '입금 제외 · 수수료 반영',
    noPnl: '손익 · 첫 체결 뒤',
    empty: '첫 확인 뒤 그래프가 그려져요',
    chartLabel: (from: string, start: string, to: string, end: string) =>
      `내 자산 ${from} ${start} → ${to} ${end}`,
    eventColumn: '사건',
  },

  tiles: {
    head: (date: string) => `${date}부터 · 장부별`,
    rebalance: '리밸런싱',
    fees: '수수료',
    checks: '확인',
    times: (n: number) => `${String(n)}회`,
    partialFailed: (n: number) => `일부 실패 ${String(n)}`,
    taxExcluded: '세금 미포함',
    failed: (n: number) => `실패 ${String(n)}`,
  },

  calendar: {
    title: '매일 확인',
    summary: (count: number, failed: number) => `확인 ${String(count)}회 중 실패 ${String(failed)}`,
    swipe: (from: string, to: string) => `가로로 밀면 ${from}~${to}`,
    legend: '범례',
    offPeriod: '끈 기간',
  },

  filters: {
    rules: '규칙',
    kinds: '종류',
    all: '전체',
    kind: {
      rebalance: '리밸런싱',
      deposit: '입금',
      withdrawal: '출금',
      dividend: '배당',
      failed: '실패',
      ai: 'AI 판단',
    },
    chip: (name: string, count: number) => `${name} ${String(count)}`,
  },

  list: {
    title: '사건 목록',
    month: (m: number) => `${String(m)}월`,
    rebalance: (pp: string) => `리밸런싱 · ${pp} 벗어남`,
    rebalancePlain: '리밸런싱',
    inProgress: '리밸런싱 중',
    partialFailed: '리밸런싱 · 일부 실패',
    checkFailed: '확인 실패',
    dividend: (krw: string) => `배당 ${krw}`,
    deposit: (krw: string) => `입금 ${krw}`,
    withdrawal: (krw: string) => `출금 ${krw}`,
    start: (krw: string) => `시작 · ${krw}`,
    offPeriod: (from: string, to: string) => `끈 기간 ${from}–${to}`,
    fees: (krw: string) => `수수료 ${krw}`,
    pending: (side: string, time: string) => `${side} ${time}`,
    retry: (date: string, filled: boolean) => (filled ? `${date} 다시 · 체결` : `${date} 다시`),
    recovered: (date: string) => `${date} 정상`,
    noChange: '—',
    before: '전',
    after: '후',
    weights: (before: string, after: string) => `전 ${before} → 후 ${after}`,
  },
} as const;

/** 처리 칩 (HistoryEvent.treatment / DayEvent.treatment). */
export const treatmentCopy = {
  'pnl-excluded': '손익 제외',
  income: '수익',
  'invest-next-check': '다음 확인에 투자',
  withdrawWait: (until: string | null) => (until ? `출금 대기 ~${until}` : '출금 대기'),
} as const;

/** 체결 라벨 (Order.fill / HistoryEvent.fill). */
export const fillCopy = {
  paper: '모의 체결',
  live: '실제 체결',
} as const;

/** Why something failed ('확인 실패 · 시세 응답 없음'). 'other' has no wording in the spec. */
export const failureCopy = {
  'no-quote': '시세 응답 없음',
  'broker-rejected': '토스 주문 거부',
  'cancel-failed': '취소 안 됨',
} as const;
