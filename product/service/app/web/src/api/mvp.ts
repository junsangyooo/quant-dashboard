// Types and React Query hooks for the MVP API (mvp/app/main.py). Field names follow the server.
import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, isApiError } from './client';

// ── 상태 · 계정 ──────────────────────────────────────────────────────────────

export interface AppState {
  setup: boolean;
  logged_in: boolean;
  unlocked: boolean;
  locked_for: number;
  /** 서버가 다시 켜진 뒤 아직 한 번도 로그인하지 않았다('앱을 다시 켰어요' 안내). */
  restarted: boolean;
  version: string;
}

// ── 연결 ────────────────────────────────────────────────────────────────────

export type StepState = 'done' | 'failed' | 'waiting';

export interface CheckStep {
  key: 'token' | 'account' | 'price';
  name: string;
  state: StepState;
}

export type CheckResult =
  | {
      ok: true;
      steps: CheckStep[];
      account_tail: string;
      price: number;
      line: string;
      at: string;
    }
  | {
      ok: false;
      kind: 'auth' | 'ip' | 'unreachable' | 'account' | 'maintenance' | 'error';
      step: string;
      step_key: string;
      steps: CheckStep[];
      title: string;
      cause: string;
      next: string;
      code: string;
      line: string;
      at: string;
    };

export interface ConnectView {
  unlocked: boolean;
  toss: {
    saved: boolean;
    client_id_tail: string | null;
    secret_tail: string | null;
    account_tail: string | null;
    last_check: CheckResult | null;
  };
}

// ── 전략 ────────────────────────────────────────────────────────────────────

export type SlotKey = 'universe' | 'signal' | 'filter' | 'select' | 'buy' | 'sell' | 'weight';
export type ModeId = 'event' | 'target' | 'rank';
export type ParamValue = number | string | boolean | string[] | null;

/** 캔버스의 조건 하나(그래프 노드). x · y는 캔버스 좌표(없으면 화면이 자동으로 놓는다). */
export interface GraphNode {
  id: string;
  piece: string;
  params: Record<string, ParamValue>;
  x: number | null;
  y: number | null;
}

export interface GraphEdge {
  from: string;
  to: string;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Body {
  name: string;
  graph: Graph;
}

export interface ParamSpec {
  key: string;
  label: string;
  unit?: string;
  min: number;
  max: number;
  integer?: boolean;
  kind?: 'symbols' | 'choice';
  options?: string[];
  range_name?: string;
}

export interface PieceSpec {
  id: string;
  slot: SlotKey;
  name: string;
  title: string;
  params: ParamSpec[];
  modes: ModeId[];
  help: string;
  help_rebalance?: string;
}

export interface SlotInfo {
  key: SlotKey;
  name: string;
  group: string;
  label: string;
  circle: string;
}

export interface Catalog {
  slots: SlotInfo[];
  pieces: Record<string, PieceSpec>;
  modes: { id: ModeId; name: string; line: string }[];
  how: { id: 'target' | 'rank'; name: string; line: string }[];
  next: Record<SlotKey, SlotKey[]>;
  limits: { nodes: number; paths: number };
  names: Record<string, string>;
  blank: Body;
  kinds: Record<ProblemKind, string>;
}

export type ProblemKind =
  'blank' | 'range' | 'required' | 'unusable' | 'loose' | 'dead' | 'rule' | 'many';

/** 서버 app/graph.py analyze()의 문제 하나. */
export interface Problem {
  kind: ProblemKind;
  /** 그 조건(노드) id. 필요한 조건 · 경로 수는 ''. */
  node: string;
  field: string;
  slot: SlotKey | '';
  /** 문제 목록 첫 줄('범위 밖 · 300일 최고가 돌파'). */
  title: string;
  /** 입력 칸 아래 · 알림 글('기간은 5~250일 사이로 입력해 주세요'). */
  short: string;
  /** 문제 목록 둘째 줄('② 신호 · 기간은 …'). */
  detail: string;
  hint: string;
}

export interface EntryPath {
  nodes: string[];
  complete: boolean;
}

export interface Analysis {
  mode: ModeId | null;
  entry: EntryPath[];
  sell: { nodes: string[] }[];
  weights: string[];
  problems: Problem[];
  counts: Partial<Record<ProblemKind, number>>;
  too_many: boolean;
}

export interface Summary {
  nodes: number;
  entry: number;
  sell: number;
  mode: ModeId | null;
  mode_name: string;
  problems: number;
  blanks: number;
}

export interface VersionRow {
  id: number;
  no: number;
  problems: number;
  blanks: number;
  created_at: string;
  paper: boolean;
}

export interface Steps {
  connected: boolean;
  strategies: number;
  backtested: boolean;
  papered: boolean;
  latest_strategy: number | null;
}

export interface StrategyListItem {
  id: number;
  name: string;
  mode: ModeId | null;
  mode_name: string;
  latest: VersionRow | null;
  summary: Summary | null;
  paper: { version_no: number } | null;
}

export interface RunRow {
  id: number;
  status: 'running' | 'ended';
  strategy: string;
  strategy_id: number;
  version_no: number;
  started_at: string;
  ended_at: string | null;
  first_d: string | null;
  last_d: string | null;
  cash0: number;
  final: number;
  ret: number;
  trades_count: number;
}

export interface StrategyDetail {
  id: number;
  name: string;
  mode: ModeId | null;
  mode_name: string;
  analysis: Analysis;
  summary: Summary;
  version: Omit<VersionRow, 'problems'> & {
    problems: Problem[];
    blanks_by_slot: { key: SlotKey; label: string; count: number }[];
  };
  body: Body;
  versions: VersionRow[];
  paper: {
    id: number;
    version_no: number;
    started_at: string;
    first_d: string | null;
    cash0: number;
    total: number;
    pnl: number;
    pnl_pct: number;
    last_d: string | null;
    held: number;
  } | null;
  past_runs: RunRow[];
  deletable: boolean;
}

export interface ExampleView {
  id: string;
  name: string;
  line: string;
  body: Body;
  summary: Summary;
  analysis: Analysis;
}

export interface CheckResult2 {
  analysis: Analysis;
  mode: ModeId | null;
  mode_name: string;
}

export interface ImportPreview {
  name: string;
  renamed: boolean;
  original_name: string;
  mode: ModeId | null;
  mode_name: string;
  source_line: string;
  body: Body;
  analysis: Analysis;
  summary: Summary;
  blanks: number;
  notes: string[];
}

// ── 백테스트 ────────────────────────────────────────────────────────────────

export interface Trade {
  d: string;
  sym: string;
  name: string;
  side: 'buy' | 'sell';
  qty: number;
  price: number;
  amount: number;
  cost: number;
  pnl: number | null;
}

export interface ReasonRow {
  slot: SlotKey | '';
  label: string;
  circle: string;
  name: string;
  text: string;
  /** 단계 번호 뒤에 그대로 쓰는 글('종목 선정 · 상위 3종목 안', '20일 최고가 돌파'). */
  display: string;
  /** 엔진이 지은 이유(조건 제목이 아님): 글 안에 단계 이름이 이미 있다. */
  special: boolean;
  close?: number;
  rank?: number;
}

export interface BacktestResult {
  start: string;
  end: string;
  days: number;
  cash: number;
  final: number;
  total: number | null;
  cagr: number | null;
  mdd: number | null;
  trades_count: number;
  buys: number;
  sells: number;
  win_rate: number | null;
  costs: number;
  curve: [string, number][];
  bench: [string, number][];
  bench_total: number | null;
  trades: (Trade & { reason: string[] })[];
  version: { id: number; no: number; strategy_id: number } | null;
  example?: { id: string; name: string };
  bench_name: string | null;
  ran_at: string;
}

// ── 모의투자 ────────────────────────────────────────────────────────────────

export interface PlanDetail {
  sym: string;
  name: string;
  side: 'buy' | 'sell';
  qty: number | null;
  value: number | null;
  judged: string;
  /** 이 계획이 체결될 시가의 날(서버: 첫 체결 규칙 반영). */
  fill_d: string;
  entry_d?: string | null;
  held_qty?: number | null;
  reasons: ReasonRow[];
}

/** 모의투자 첫 확인 · 첫 모의 체결(서버 app/paper.py first_schedule이 정한 한 값). */
export interface FirstSchedule {
  check_now: boolean;
  check_d: string;
  check_time: string;
  bar_d: string;
  fill_d: string;
}

export interface Judgement {
  d: string;
  made_at: string;
  how: 'start' | 'button' | 'auto';
}

export interface AutoInfo {
  at: string;
  last: string | null;
  last_result: string | null;
  last_fill: {
    run_id: number;
    new_days: number;
    /** 이어 채운 날 가운데 앱이 꺼져 있던 날(그날 16:30 자동 확인이 돌지 않은 날). */
    off_days?: string[];
    from: string | null;
    to: string;
    at: string;
  } | null;
  now: string;
}

export interface Holding {
  sym: string;
  name: string;
  qty: number;
  avg: number;
  price: number;
  price_d: string;
  prev_close: number | null;
  day_pnl: number | null;
  day_pct: number | null;
  value: number;
  /** 매입금액(수량 × 평균 단가, 매수 수수료 포함). */
  cost: number;
  pnl: number;
  pnl_pct: number | null;
  entry_d: string;
  weight: number | null;
  /** 최근 30일 종가(작은 그래프). */
  spark: number[];
  /** 매수 이유(마지막 매수 체결의 이유 글). */
  reasons: ReasonRow[];
}

export interface RecentTrade {
  d: string;
  sym: string;
  name: string;
  side: 'buy' | 'sell';
  qty: number;
  price: number;
  amount: number;
  reasons: ReasonRow[];
}

export type HomeResponse =
  | {
      running: false;
      had_run: boolean;
      last_run:
        | (RunRow & {
            last_eval_d: string | null;
            held_end: number;
            realized: number;
            buys: number;
            sells: number;
            costs: number;
            curve: [string, number][];
          })
        | null;
      recent?: RecentTrade[];
      auto: AutoInfo;
      steps: Steps;
    }
  | {
      running: true;
      run_id: number;
      strategy: string;
      strategy_id: number;
      version_no: number;
      version_id: number;
      started_at: string;
      last_judged: string;
      cash0: number;
      cash: number;
      stock_value: number;
      cost: number;
      total: number;
      pnl: number;
      pnl_pct: number;
      day_pnl: number | null;
      day_pct: number | null;
      equity_change: number | null;
      sold_today: number;
      curve: [string, number][];
      holdings: Holding[];
      plans: PlanDetail[];
      last: Judgement | null;
      first: FirstSchedule | null;
      price_as_of: { kind: 'toss'; at: string } | { kind: 'yahoo'; d: string };
      recent: RecentTrade[];
      trades_count: number;
      auto: AutoInfo;
      steps: Steps;
    };

export type PlanResponse =
  | { running: false; auto: AutoInfo }
  | {
      running: true;
      run_id: number;
      strategy: string;
      strategy_id: number;
      version_no: number;
      last_judged: string;
      last: Judgement | null;
      plans: PlanDetail[];
      keep: { sym: string; name: string }[];
      held: number;
      started_at: string;
      first: FirstSchedule | null;
      auto: AutoInfo;
    };

export interface JudgeResult {
  new_days: number;
  first: string | null;
  judged: string;
  message: string;
  at: string;
}

export interface RunView {
  id: number;
  status: 'running' | 'ended';
  strategy: string;
  strategy_id: number;
  version_no: number;
  started_at: string;
  ended_at: string | null;
  first_d: string | null;
  last_d: string | null;
  cash0: number;
  final: number;
  ret: number | null;
  realized: number;
  trades_count: number;
  buys: number;
  sells: number;
  costs: number;
  first: FirstSchedule | null;
  last_eval_d: string | null;
  held_end: number;
  trades: (Trade & { reasons: ReasonRow[] })[];
}

// ── 쿼리 ────────────────────────────────────────────────────────────────────

export const keys = {
  state: ['state'] as const,
  connect: ['connect'] as const,
  catalog: ['catalog'] as const,
  strategies: ['strategies'] as const,
  examples: ['examples'] as const,
  example: (id: string) => ['example', id] as const,
  strategy: (id: number) => ['strategy', id] as const,
  home: ['home'] as const,
  plan: ['plan'] as const,
  runs: (strategyId?: number) => ['runs', strategyId ?? 'all'] as const,
  run: (id: number) => ['run', id] as const,
};

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5_000,
        refetchOnWindowFocus: false,
        // A 4xx answer will not change on retry; a dropped connection may.
        retry: (count, error) => !isApiError(error) && count < 2,
      },
    },
  });
}

export const useAppState = () =>
  useQuery({ queryKey: keys.state, queryFn: () => api.get<AppState>('/api/state') });
export const useConnect = () =>
  useQuery({ queryKey: keys.connect, queryFn: () => api.get<ConnectView>('/api/connect') });
export const useCatalog = () =>
  useQuery({
    queryKey: keys.catalog,
    queryFn: () => api.get<Catalog>('/api/catalog'),
    staleTime: Infinity,
  });
export const useStrategies = () =>
  useQuery({
    queryKey: keys.strategies,
    queryFn: () => api.get<{ strategies: StrategyListItem[]; steps: Steps }>('/api/strategies'),
  });
export const useExamples = () =>
  useQuery({
    queryKey: keys.examples,
    queryFn: () => api.get<{ examples: ExampleView[] }>('/api/examples'),
    staleTime: Infinity,
  });
export const useExample = (id: string, enabled = true) =>
  useQuery({
    queryKey: keys.example(id),
    queryFn: () => api.get<ExampleView>(`/api/examples/${encodeURIComponent(id)}`),
    staleTime: Infinity,
    enabled,
  });
export const useStrategy = (id: number, enabled = true) =>
  useQuery({
    queryKey: keys.strategy(id),
    queryFn: () => api.get<StrategyDetail>(`/api/strategies/${String(id)}`),
    enabled,
  });
export const useHome = () =>
  useQuery({ queryKey: keys.home, queryFn: () => api.get<HomeResponse>('/api/home') });
export const usePlan = () =>
  useQuery({ queryKey: keys.plan, queryFn: () => api.get<PlanResponse>('/api/plan') });
export const usePreview = (versionId: number) =>
  useQuery({
    queryKey: ['preview', versionId],
    queryFn: () => api.get<FirstSchedule>('/api/paper/preview', { version_id: versionId }),
    staleTime: 0,
  });
export const useRuns = (strategyId?: number) =>
  useQuery({
    queryKey: keys.runs(strategyId),
    queryFn: () =>
      api.get<{ runs: RunRow[]; auto: AutoInfo }>(
        '/api/paper/runs',
        strategyId === undefined ? undefined : { strategy_id: strategyId },
      ),
  });
export const useRun = (id: number | null) =>
  useQuery({
    queryKey: keys.run(id ?? 0),
    queryFn: () => api.get<RunView>(`/api/paper/runs/${String(id ?? 0)}`),
    enabled: id !== null,
  });

/** Everything that a paper or strategy change can move. */
export function useRefreshAll() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries();
}

export function usePost<TBody, TOut>(path: string | ((b: TBody) => string), method = 'POST') {
  const refresh = useRefreshAll();
  return useMutation({
    mutationFn: (b: TBody) => {
      const url = typeof path === 'string' ? path : path(b);
      if (method === 'PUT') return api.put<TOut>(url, b);
      if (method === 'DELETE') return api.delete<TOut>(url);
      return api.post<TOut>(url, b);
    },
    onSuccess: () => void refresh(),
  });
}
