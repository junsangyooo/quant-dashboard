// Fixture bundles (autotrade/CONTRACT.md §화면 상태와 고정 자료): the endpoint responses one
// screen state needs, plus its fixed `now`. Bundles live in src/fixtures/bundles/<state id>.ts
// and are type-checked against src/api/types.ts. They never reach the production build.
import type {
  AccountResponse,
  ApiErrorBody,
  Breakdown,
  CancelRetryResponse,
  DayResponse,
  HealthResponse,
  HistoryResponse,
  HomeResponse,
  LiveOffResponse,
  LiveOnResponse,
  ModeResponse,
  NotificationsResponse,
  PlanResponse,
  PushTestResponse,
  RuleDetailResponse,
  RulesListResponse,
  ShellResponse,
} from '../api/types';

/** State ids from the contract; one per Figma 디자인 frame (plus states drawn only in the spec). */
export type StateId =
  | 'home.paper'
  | 'home.live'
  | 'home.live-first'
  | 'home.withdraw'
  | 'home.stale'
  | 'home.partial'
  | 'home.offline'
  | 'home.other-device'
  | 'home.first-day'
  | 'home.empty'
  | 'plan.paper'
  | 'plan.live'
  | 'plan.stale'
  | 'plan.partial'
  | 'plan.live-todo'
  | 'plan.first-day'
  | 'history.paper'
  | 'history.paper-ledger'
  | 'day.0821'
  | 'day.0925'
  | 'rules.index-half'
  | 'rules.momentum'
  | 'rules.first-day'
  | 'health.todo'
  | 'health.stale'
  | 'health.unknown'
  | 'health.failed'
  | 'mode.paper'
  | 'mode.live'
  | 'mode.turning-on'
  | 'mode.off-confirm'
  | 'mode.off-failed'
  | 'mode.blocked'
  | 'mode.short'
  | 'account.default'
  | 'account.no-push'
  | 'pin.entering'
  | 'pin.error'
  | 'pin.locked';

/** The request never gets a response (the client raises NetworkError → '연결 안 됨'). */
export interface NetworkDown {
  $network: 'down';
}

/** An HTTP error with the contract's JSON body (403 `{error:'pin', remaining}` …). */
export interface HttpFailure {
  $status: number;
  $body: ApiErrorBody & Record<string, unknown>;
}

/** 204 No Content (writes like POST /api/auth/pin). */
export interface NoContent {
  $noContent: true;
}

export type Step<T> = T | NetworkDown | HttpFailure;

/** One response, or a sequence: call n gets step n and the last step repeats. */
export type Script<T> = Step<T> | readonly Step<T>[];

export interface FixtureResponses {
  '/api/shell'?: Script<ShellResponse>;
  '/api/home'?: Script<HomeResponse>;
  '/api/home/breakdown'?: Script<Breakdown>;
  '/api/plan'?: Script<PlanResponse>;
  '/api/history'?: Script<HistoryResponse>;
  '/api/rules'?: Script<RulesListResponse>;
  '/api/health'?: Script<HealthResponse>;
  '/api/mode'?: Script<ModeResponse>;
  '/api/account'?: Script<AccountResponse>;
  [day: `/api/day/${string}`]: Script<DayResponse>;
  [rule: `/api/rules/${string}`]: Script<RuleDetailResponse>;
  // Query-specific variants win over the bare path, e.g. '/api/home?ledger=paper&period=1y'.
  [home: `/api/home?${string}`]: Script<HomeResponse>;
  [plan: `/api/plan?${string}`]: Script<PlanResponse>;
  [history: `/api/history?${string}`]: Script<HistoryResponse>;
  // Writes are keyed by method; unscripted writes answer 404 'not-in-fixture'.
  'POST /api/auth/pin'?: Script<NoContent>;
  'POST /api/auth/logout'?: Script<NoContent>;
  'POST /api/auth/logout-others'?: Script<NoContent>;
  'POST /api/account/pin'?: Script<NoContent>;
  'POST /api/mode/live'?: Script<LiveOnResponse>;
  'POST /api/mode/paper'?: Script<LiveOffResponse>;
  'POST /api/mode/cancel-retry'?: Script<CancelRetryResponse>;
  'PUT /api/account/notifications'?: Script<NotificationsResponse>;
  'POST /api/account/push'?: Script<NoContent>;
  'POST /api/account/push/test'?: Script<PushTestResponse>;
}

export interface FixtureBundle {
  id: StateId;
  /** Server time of the state (KST ISO); the shell's `now` should match it. */
  now: string;
  /** Faster /api/shell polling for scripted sequences (offline, other-device). Default 60 s. */
  shellPollMs?: number;
  responses: FixtureResponses;
}
