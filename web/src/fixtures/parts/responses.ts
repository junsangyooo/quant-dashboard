// The /api/home · /api/home/breakdown · /api/plan answers of one world, with the query variants
// the screens ask for (period and drift chips). home.* and plan.* bundles of the same world
// share them, so moving between 자산 and 계획 inside one fixture shows one consistent state.
import type { FixtureResponses } from '../types';
import { paperDays } from './day';
import { historyPaper } from './history';
import {
  STALE_BREAKDOWN,
  homeLive,
  homeLiveTodo,
  homePaper,
  homePartial,
  homeStale,
  homeWithdraw,
  paperBreakdown,
} from './home';
import {
  paperDrift,
  planLive,
  planLiveTodo,
  planPaper,
  planPartial,
  planStale,
  planWithdraw,
} from './plan';

/** 모의투자 기본 (10/7 16:10): 3개월 by default, 1개월 · 1년 · 전체 and drift 1년 · 전체. */
export function paperResponses(): FixtureResponses {
  return {
    // The day panels the markers open and 기록 behind them on 1440 (SCR-DAY / SCR-HISTORY world).
    ...paperDays(),
    '/api/history': historyPaper(),
    '/api/home': homePaper('3m'),
    '/api/home?ledger=paper&period=1m': homePaper('1m'),
    '/api/home?ledger=paper&period=1y': homePaper('1y'),
    '/api/home?ledger=paper&period=all': homePaper('all'),
    '/api/home/breakdown': paperBreakdown('3m'),
    '/api/home/breakdown?ledger=paper&period=1m': paperBreakdown('1m'),
    '/api/home/breakdown?ledger=paper&period=1y': paperBreakdown('1y'),
    '/api/plan': planPaper('3m'),
    '/api/plan?ledger=paper&drift=1y': planPaper('1y'),
    '/api/plan?ledger=paper&drift=all': { ...planPaper('all'), drift: paperDrift('all') },
  };
}

/** 일부 실패 (10/8 08:40). */
export function partialResponses(): FixtureResponses {
  return {
    '/api/home': homePartial(),
    '/api/home/breakdown': paperBreakdown('3m'),
    '/api/plan': planPartial(),
  };
}

/** 시세 대기 (10/7 16:10). */
export function staleResponses(): FixtureResponses {
  return {
    '/api/home': homeStale(),
    '/api/home/breakdown': STALE_BREAKDOWN,
    '/api/plan': planStale(),
  };
}

/** 실전 평상 (10/7 16:10): 27거래일, no period chips. */
export function liveResponses(): FixtureResponses {
  return { '/api/home': homeLive(), '/api/plan': planLive() };
}

/** 실전 일부 실패 · 직접 할 일 (10/8 08:40). */
export function liveTodoResponses(): FixtureResponses {
  return { '/api/home': homeLiveTodo(), '/api/plan': planLiveTodo() };
}

/** 실전 출금 대기 (10/7 16:10). */
export function withdrawResponses(): FixtureResponses {
  return { '/api/home': homeWithdraw(), '/api/plan': planWithdraw() };
}
