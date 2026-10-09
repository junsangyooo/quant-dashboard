// SCR-ACCOUNT 설정. Sources: 기획.md §5 SCR-ACCOUNT (lines 800–848), Figma 1:65384 · 1:65568,
// 예시-값표 §3 (알림 불가), 화면-맞춤.md §3 (AI 알림 사건 셋). Strings marked NEW are not in the
// spec or Figma; they follow its pattern.
import type { NotifyEvent } from '../api/types';

export const accountCopy = {
  pin: {
    title: 'PIN 바꾸기',
    note: '바꾸면 다른 기기는 다시 들어와야 해요',
    /** Spec: '펼친 칸 3개(현재·새·새 다시)'. */
    current: '현재 PIN',
    next: '새 PIN',
    again: '새 PIN 다시',
    /** NEW */
    submit: '바꾸기',
    busy: '바꾸는 중',
    done: '바꿨어요 · 다른 기기 로그아웃됨',
    wrongCurrent: '현재 PIN이 맞지 않아요',
    mismatch: '두 PIN이 달라요',
    /** NEW — 400 invalid-pin. */
    invalid: '6자리 숫자로 넣어요',
    /** NEW */
    failed: '바꾸지 못했어요 · 다시 시도',
  },

  devices: {
    title: '기기',
    /** The home-screen app has no browser in its name: 'iPhone · 홈 화면 앱'. */
    homeScreenApp: '홈 화면 앱',
    enteredAt: (at: string) => `들어온 시각 ${at}`,
    thisDevice: '이 기기',
    logout: '로그아웃',
    lost: '휴대폰을 잃어버렸을 때',
    logoutOthers: '다른 기기 모두 로그아웃',
    /** NEW — the confirm modal (spec: '확인 모달(그림 없음)'). */
    confirmTitle: '다른 기기를 모두 로그아웃할까요?',
    confirmBody: '이 기기만 남고 다른 기기는 PIN을 다시 넣어야 해요',
    cancel: '취소',
    confirm: '로그아웃',
    /** NEW */
    othersDone: '다른 기기 로그아웃됨',
    /** NEW */
    failed: '로그아웃하지 못했어요 · 다시 시도',
  },

  notifications: {
    title: '알림',
    thisDevice: '이 기기에서 알림 받기',
    iphoneOnly: 'iPhone은 홈 화면 앱에서만 받아요',
    /** Empty state (0 devices): above the switch. */
    start: '이 기기에서 알림 받기를 눌러 시작해요',
    cannot: (reason: string) => `이 기기는 알림을 못 받아요 · ${reason}`,
    reasons: {
      'safari-tab': 'Safari 탭',
      /** NEW */
      denied: '알림 차단됨',
      unsupported: '지원 안 됨',
    },
    fix: {
      'safari-tab': '공유 → 홈 화면에 추가 → 앱에서 다시 켜기',
      /** NEW — spec recovery: '브라우저 설정 허용 후 다시 켜기'. */
      denied: '브라우저 설정 → 알림 허용 → 다시 켜기',
    },
    /** NEW — phase 1: push answers 501 not-implemented. */
    notReady: '알림은 준비 중이에요 · 다음 단계에서 켤 수 있어요',
    /** NEW — turning this device off has no endpoint yet. */
    offNotReady: '이 기기 알림 끄기는 준비 중이에요',
    /** NEW */
    subscribeFailed: '켜지 못했어요 · 다시 시도',
    eventsTitle: (n: number) => `받을 사건 · 처음부터 ${String(n)}개 켜짐`,
    hideAmounts: '알림에 금액 숨기기',
    saved: (at: string) => `${at} 저장됨`,
    /** NEW */
    saving: '저장 중',
    /** NEW */
    saveFailed: '저장하지 못했어요 · 다시 시도',
    test: '시험 알림 보내기',
    /** NEW */
    testing: '보내는 중',
    /** NEW */
    testNotReady: '시험 알림은 준비 중이에요',
    /** NEW */
    testFailed: '보내지 못했어요 · 다시 시도',
    received: (at: string) => `${at} 받음`,
    resultFailed: '실패',
    /** NEW — screen-reader word for the lock icon. */
    locked: '끌 수 없음',
  },

  /** 사건 스위치 9개 (1:39291) + AI 사건 3개 (2단계, 화면-맞춤 §3 — labels NEW). */
  events: {
    'check-failed': { name: '확인 실패', note: '일부 실패 포함 · 끌 수 없어요' },
    stale: { name: '자료 낡음' },
    'weekly-ok': { name: '주간 정상 요약', note: '끄면 서버가 멈춰도 알 수 없게 돼요' },
    'live-fill': { name: '실전 체결' },
    'pin-failures': { name: 'PIN 실패 급증' },
    'toss-expiring': { name: '토스 연결 만료 예정' },
    'check-missed': { name: '확인 누락' },
    'rebalance-notice': { name: '리밸런싱 예고' },
    'cash-moves': { name: '입출금·직접 매매' },
    /** NEW — 'AI가 팔기로 함' (화면-맞춤 §3), default on because real money moves. */
    'ai-sell': { name: 'AI 매도 결정', note: '실전이면 실제 돈이 움직여요' },
    /** NEW — '새 종목 매수'. */
    'ai-buy': { name: 'AI 새 종목 매수' },
    /** NEW — '월 점검·분기 발굴 결과'. */
    'ai-review': { name: 'AI 점검·발굴 결과', note: '판정이 바뀐 종목만 알려요' },
  } satisfies Record<NotifyEvent, { name: string; note?: string }>,

  /** NEW */
  error: '설정을 못 불러왔어요',
} as const;
