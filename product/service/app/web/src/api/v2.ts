// Types and hooks for the v2 strategy API (app/api_v2.py): block bodies, catalog, analysis.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';

export type StageId = 'universe' | 'signal' | 'filter' | 'select' | 'buy' | 'sell' | 'weight';
export type Match = 'all' | 'any';
export type ExecId = 'intraday' | 'broker' | 'close';
export type RowValue = number | string | string[] | null;

export interface Row {
  item: string;
  op: string;
  params: Record<string, number | string | null>;
  value: RowValue;
  value2: number | null;
  exec: ExecId | null;
}

export interface Block {
  id: string;
  stage: StageId;
  match: Match;
  rows: Row[];
  x: number;
  y: number;
}

export interface Edge {
  from: string;
  to: string;
}

export interface Body {
  name: string;
  graph: { blocks: Block[]; edges: Edge[] };
  converted?: string;
}

export interface CatalogParam {
  key: string;
  label: string;
  choices: string[];
  min: number | null;
  max: number | null;
  integer: boolean | null;
  when_op: string[];
}

export interface CatalogItem {
  id: string;
  name: string;
  short: string;
  category: string;
  ops: string[];
  op_names: string[];
  stages: StageId[];
  sortable: boolean;
  lock: string | null;
  backtest: 'yes' | 'partial' | 'no';
  backtest_display: string;
  chips: string[];
  execs: ExecId[];
  unit: string;
  source: string;
  source_display: string;
  start: string | null;
  start_reason: string | null;
  params: CatalogParam[];
  value: { min: number; max: number; unit: string; integer: boolean } | null;
  rank: { min: number; max: number } | null;
  choices: string[];
  help: string;
}

export interface CatalogStage {
  id: StageId;
  circle: string;
  name: string;
  once: boolean;
  toggle: boolean;
}

export interface Catalog {
  items: CatalogItem[];
  stages: CatalogStage[];
  ops: Record<string, string>;
  execs: Record<ExecId, string>;
  categories: string[];
  dart: boolean;
}

export interface Problem {
  kind: string;
  title: string;
  detail: string;
  block: string;
  row: number | null;
  stage: StageId | '';
}

export interface Path {
  blocks: string[];
  complete?: boolean;
}

export interface Analysis {
  mode: 'event' | 'target' | 'rank' | null;
  mode_name: string;
  entry: Path[];
  sell: Path[];
  weight: string | null;
  problems: Problem[];
  warnings: Problem[];
  summary: { title: string; line: string };
  has_stop: boolean;
}

export interface ExecChip {
  exec: ExecId;
  name: string;
  reason: string;
}

export interface BodyView {
  analysis: Analysis;
  sentence: string;
  chips: Record<string, (ExecChip | null)[]>;
  row_texts: Record<string, string[]>;
  start: { date: string; reason: string } | null;
}

export interface StrategyV2 extends BodyView {
  id: number;
  name: string;
  version: { id: number; no: number };
  versions: { id: number; no: number; problems: number; created_at: string }[];
  body: Body;
  running: { kind: string; version_no: number } | null;
}

export const v2keys = {
  catalog: ['v2', 'catalog'] as const,
  strategy: (id: number) => ['v2', 'strategy', id] as const,
  analyze: (body: string) => ['v2', 'analyze', body] as const,
};

export const useCatalog = () =>
  useQuery({
    queryKey: v2keys.catalog,
    queryFn: () => api.get<Catalog>('/api/v2/catalog'),
    staleTime: 60_000,
  });

export const useStrategyV2 = (id: number | null) =>
  useQuery({
    queryKey: v2keys.strategy(id ?? 0),
    queryFn: () => api.get<StrategyV2>(`/api/v2/strategies/${String(id)}`),
    enabled: id !== null,
  });

/** Server analysis of the body being edited (problems, warnings, chips, sentence). */
export const useAnalysis = (body: Body | null) => {
  const text = body ? JSON.stringify(body) : '';
  return useQuery({
    queryKey: v2keys.analyze(text),
    queryFn: () => api.post<BodyView & { body: Body }>('/api/v2/analyze', { body }),
    enabled: body !== null,
    placeholderData: (prev) => prev,
    staleTime: Infinity,
  });
};

export function useSaveStrategy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number | null; body: Body }) =>
      id === null
        ? api.post<{ id: number; no: number; problems: number }>('/api/v2/strategies', { body })
        : api
            .post<{ no: number; problems: number }>(`/api/v2/strategies/${String(id)}/versions`, {
              body,
            })
            .then((r) => ({ ...r, id })),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: v2keys.strategy(r.id) });
      void qc.invalidateQueries({ queryKey: ['strategies'] });
    },
  });
}

// ── 목록 · 상세 · 가져오기(T-31) ─────────────────────────────────────────────

export interface VersionView {
  id: number;
  no: number;
  problems: number;
  created_at: string;
  saved_day: string;
  saved_hm: string;
  backtested: boolean;
  backtested_hm: string;
}

export interface StrategyCard {
  id: number;
  name: string;
  mode_name: string;
  problems: number;
  version: VersionView;
  running: { kind: string; version_no: number } | null;
}

export interface StrategyDetail extends Omit<StrategyV2, 'version' | 'versions'> {
  version: VersionView;
  versions: VersionView[];
  deletable: boolean;
  block_lines: Record<string, string[]>;
}

export interface ImportPreview {
  body: Body;
  notes: string[];
  name: string;
  stages: number;
  entry: number;
  sell: number;
  rows: number;
  blanks: number;
  blank_kinds: string[];
  cards: { id: string; stage: StageId; match: Match; lines: string[] }[];
  others: StageId[];
}

export const useStrategyList = () =>
  useQuery({
    queryKey: ['strategies', 'v2'],
    queryFn: () => api.get<{ strategies: StrategyCard[] }>('/api/v2/strategies'),
  });

export const useStrategyDetail = (id: number) =>
  useQuery({
    queryKey: v2keys.strategy(id),
    queryFn: () => api.get<StrategyDetail>(`/api/v2/strategies/${String(id)}`),
  });

export const previewImport = (text: string) =>
  api.post<ImportPreview>('/api/v2/import/preview', { text });
export const acceptImport = (text: string) =>
  api.post<{ id: number; name: string }>('/api/v2/import/accept', { text });
export const importFile = (text: string) =>
  api.post<{ id: number; name: string }>('/api/v2/import/file', { text });
export const exportFile = (id: number) =>
  api.get<{ name: string; text: string }>(`/api/v2/strategies/${String(id)}/file`);
export const copyText = (id: number) =>
  api.get<{ text: string }>(`/api/v2/strategies/${String(id)}/copytext`);
export const deleteStrategy = (id: number) =>
  api.delete<{ ok: boolean }>(`/api/v2/strategies/${String(id)}`);

// ── 백테스트(T-32) ────────────────────────────────────────────────────────────

export interface BacktestInput {
  version: VersionView;
  strategy_id: number;
  name: string;
  range: { start: string; end: string; first: string; reason: string };
  chips: string[];
  judge_line: string;
}

export interface BacktestTrade {
  d: string;
  sym: string;
  name: string;
  side: 'buy' | 'sell';
  qty: number;
  price: number;
  pnl: number | null;
}

export interface BacktestV2Result {
  start: string;
  end: string;
  final: number;
  total: number | null;
  cagr: number | null;
  mdd: number | null;
  win_rate: number | null;
  costs: number;
  trade_count: number;
  recent: BacktestTrade[];
  curve: [string, number][];
  bench_curve: [string, number][];
  bench_total: number | null;
  live_note: string;
  live_counts: { no_buy: number; no_sell: number };
  survivor_line: string;
  wide_universe: boolean;
  wide_title: string;
  ran_day: string;
  ran_hm: string;
}

export const useBacktestInput = (vid: number | null) =>
  useQuery({
    queryKey: ['v2', 'backtest-input', vid],
    queryFn: () => api.get<BacktestInput>(`/api/v2/versions/${String(vid)}/backtest`),
    enabled: vid !== null,
  });

export const runBacktestV2 = (b: {
  version_id: number;
  start: string;
  end: string;
  cash: number;
}) => api.post<BacktestV2Result>('/api/v2/backtest', b);

// ── 모의투자(T-41) ────────────────────────────────────────────────────────────

export interface PaperTrade {
  d: string;
  symbol: string;
  side: 'buy' | 'sell';
  qty: number;
  price: number;
  amount: number;
  pnl: number | null;
}

export interface PaperRunV2 {
  id: number;
  status: 'running' | 'ended';
  strategy_id: number | null;
  name: string;
  version_no: number | null;
  cash0: number;
  cash: number;
  total: number;
  return: number;
  holdings: { sym: string; qty: number; avg: number }[];
  plans: { sym: string; side: 'buy' | 'sell'; value?: number; qty?: number; reason: string[] }[];
  trades: PaperTrade[];
  curve: [string, number][];
  last_date: string | null;
  started_at: string;
  ended_at: string | null;
  diff_line: string;
  first_check: string;
  bench_return: number | null;
}

export interface PaperPreview {
  name: string;
  version_no: number;
  limits: string;
  line: string;
  already: string;
  running_id: number | null;
  check: string;
  fill: string;
  first_line: string;
}

export const usePaperRuns = () =>
  useQuery({
    queryKey: ['v2', 'paper'],
    queryFn: () => api.get<{ runs: PaperRunV2[] }>('/api/v2/paper'),
  });
export const usePaperRun = (id: number) =>
  useQuery({
    queryKey: ['v2', 'paper', id],
    queryFn: () => api.get<PaperRunV2>(`/api/v2/paper/${String(id)}`),
  });
export const usePaperPreview = (vid: number) =>
  useQuery({
    queryKey: ['v2', 'paper-preview', vid],
    queryFn: () => api.get<PaperPreview>('/api/v2/paper/preview', { version_id: vid }),
  });
export const startPaper = (version_id: number, cash: number) =>
  api.post<PaperRunV2>('/api/v2/paper/start', { version_id, cash });
export const stopPaper = (id: number) => api.post<PaperRunV2>(`/api/v2/paper/${String(id)}/stop`);
