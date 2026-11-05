// Shared screen words (header, tabs, units, common buttons). Each screen's own words live in
// copy/*.ts. Sources: the MVP Figma frames and product/service/GLOSSARY.md.
// Labels are short nouns; sentences use 해요체.

import { texts } from './copy/texts.gen';

export const copy = {
  wordmark: 'quant',

  /** Units and weekday names used by lib/format. */
  units: {
    won: '원',
    eok: '억',
    man: '만',
    pp: '%p',
    shares: '주',
    times: '회',
    stocks: '종목',
    days: '거래일',
  },
  weekdaysShort: ['일', '월', '화', '수', '목', '금', '토'] as const,
  skipLink: '본문으로 건너뛰기',
  back: '뒤로',
  close: '닫기',
  settings: '설정',

  /** Header: the MVP is paper-only, always. */
  mode: { paper: '모의투자' },

  nav: {
    home: '자산',
    plan: '계획',
    history: '기록',
    strategies: '전략',
    paper: '모의투자',
  },

  pages: {
    setup: texts.password_create,
    login: '로그인',
    recover: texts.password_recover,
    home: '자산',
    plan: '계획',
    history: '기록',
    strategies: '전략',
    strategy: '전략 상세',
    editor: '전략 편집',
    backtest: '백테스트',
    import: texts.paste_strategy,
    paper: '모의투자',
    todos: texts.todos_alerts,
    liveStart: texts.live_start,
    paperRun: '모의투자 상세',
    paperStart: '모의투자 시작',
    settings: '설정',
    connect: '연결',
    password: '비밀번호 변경',
    terms: '사용 조건',
    about: '앱 정보',
    notFound: '없는 화면',
  },

  common: {
    next: '다음',
    copy: '복사',
    copied: '복사했어요',
    dismiss: '취소',
    save: '저장',
    delete: '삭제',
    toStrategies: '전략으로',
    retry: '다시 불러오기',
    loadFailed: '불러오지 못했어요',
    noConnection: '앱에 연결할 수 없어요 · 앱이 켜져 있는지 확인해 주세요',
    unknownError: texts.unknown_error,
    buy: '매수',
    sell: '매도',
    dash: '—',
    version: (n: number) => texts.version({ n }),
    paperRunning: '모의투자 중',
    backtestReady: '백테스트 가능',
    problems: (n: number) => `문제 ${String(n)}개`,
    localOnly: '이 컴퓨터(127.0.0.1)에서만 열려요',
    notFoundBody: '주소가 맞는지 확인해 주세요',
    toHome: '자산으로',
  },
} as const;
