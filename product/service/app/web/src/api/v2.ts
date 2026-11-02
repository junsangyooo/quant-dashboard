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
