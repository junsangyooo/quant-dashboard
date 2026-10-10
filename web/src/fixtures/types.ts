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
  // SCR-HOME states drawn only in the spec (기획 §5 상태 표)
  | 'home.holiday'
  | 'home.loading'
  | 'home.check-failed'
  | 'home.live-todo'
  | 'home.push-undelivered'
  | 'home.permission'
  | 'plan.paper'
  | 'plan.live'
  | 'plan.stale'
  | 'plan.partial'
  | 'plan.live-todo'
  | 'plan.first-day'
  // SCR-PLAN states drawn only in the spec, plus the AI-rule card (Figma 탐색 17:7108)
  | 'plan.empty'
  | 'plan.withdraw'
  | 'plan.holiday'
  | 'plan.loading'
  | 'plan.offline'
  | 'plan.permission'
  | 'plan.discovery'
  | 'history.paper'
  | 'history.paper-ledger'
  // SCR-HISTORY states drawn only in the spec (기획 §5 상태 표)
  | 'history.off-period'
  | 'history.empty'
  | 'history.loading'
  | 'history.error'
  | 'history.offline'
  | 'history.stale'
  | 'history.permission'
  | 'day.0821'
  | 'day.0925'
  // SCR-DAY states drawn only in the spec, plus 10/7 (리밸런싱 중 + AI 판단 카드, no drawing)
  | 'day.partial'
  | 'day.1007'
  | 'day.ai'
  | 'day.weekend'
  | 'day.loading'
  | 'day.error'
  | 'day.permission'
  | 'rules.index-half'
  | 'rules.momentum'
  | 'rules.first-day'
  // SCR-RULES states drawn only in the spec, plus the 3년 발굴 lanes (Figma 탐색 17:5855 …)
  | 'rules.loading'
  | 'rules.error'
  | 'rules.stale'
  | 'rules.permission'
  | 'rules.discovery-daily'
  | 'rules.discovery-quarterly'
  | 'rules.discovery-earnings'
  | 'rules.discovery-monthly'
  | 'health.todo'
  | 'health.stale'
  | 'health.unknown'
  | 'health.failed'
  // SCR-HEALTH states drawn only in the spec, plus the 2단계 source rows (화면-맞춤 §3)
  | 'health.empty'
  | 'health.loading'
  | 'health.permission'
  | 'health.phase2'
  | 'mode.paper'
  | 'mode.live'
  | 'mode.turning-on'
  | 'mode.off-confirm'
  | 'mode.off-failed'
  | 'mode.blocked'
  | 'mode.short'
  // SCR-MODE states drawn only in the spec, plus phase 1 (409 live-not-available)
  | 'mode.empty'
  | 'mode.loading'
  | 'mode.live-stale'
  | 'mode.live-not-available'
  | 'mode.preview-changed'
  | 'mode.permission'
  | 'account.default'
  | 'account.no-push'
  // SCR-ACCOUNT states drawn only in the spec, plus phase 1 (push 501)
  | 'account.empty'
  | 'account.loading'
  | 'account.error'
  | 'account.pin-error'
  | 'account.push-not-ready'
  | 'account.permission'
  | 'pin.entering'
  | 'pin.error'
  | 'pin.locked'
  // SCR-PIN states drawn only in the spec, plus 403 no-pin (CONTRACT.md)
  | 'pin.global-lock'
  | 'pin.no-pin'
  | 'pin.loading'
  // 403 locked scope 'hold': new logins closed until the server's unlock (CONTRACT.md 쓰기)
  | 'pin.hold';

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

/** The request stays open and never answers (loading states). */
export interface Pending {
  $pending: true;
}

/** The answer arrives after a delay (a skeleton that then fills, e.g. home.other-device). */
export interface Delayed<T> {
  $delayMs: number;
  $then: T;
}

/**
 * Answers `$before` until the page has made the write `$afterWrite` (e.g. 'POST /api/mode/paper'),
 * then `$after` — however many times the read is repeated (the shell refetches on every mount).
 */
export interface AfterWrite<T> {
  $afterWrite: string;
  $before: Step<T>;
  $after: Step<T>;
}

export type Step<T> = T | NetworkDown | HttpFailure | Pending | Delayed<T> | AfterWrite<T>;

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
  [breakdown: `/api/home/breakdown?${string}`]: Script<Breakdown>;
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
  'DELETE /api/account/push'?: Script<NoContent>;
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
