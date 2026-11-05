// Types and hooks for the v2 strategy API (app/api/strategies.py · paper: app/api/paper.py): block bodies, catalog,
// analysis. Response types are the server's response models (types.gen.ts · no hand-written API types · P1-09).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type { components } from './types.gen';

type Schemas = components['schemas'];

export type Body = Schemas['Body'];
export type Block = Schemas['Block'];
export type Row = Schemas['Row'];
export type Edge = Schemas['Edge'];
export type StageId = Block['stage'];
export type Match = Block['match'];
export type ExecId = Schemas['ExecChip']['exec'];
export type RowValue = Row['value'];
export type Catalog = Schemas['Catalog'];
export type CatalogItem = Schemas['CatalogItem'];
export type CatalogParam = Schemas['CatalogParam'];
export type CatalogStage = Schemas['CatalogStage'];
export type Problem = Schemas['Problem'];
export type Path = Schemas['StrategyPath'];
export type Analysis = Schemas['Analysis'];
export type ExecChip = Schemas['ExecChip'];
/** Server analysis of a body (`POST /api/v2/analyze`): the body plus problems, warnings, chips, sentence. */
export type Analyzed = Schemas['Analyzed'];
export type BodyView = Omit<Analyzed, 'body'>;
export type StrategyV2 = Schemas['StrategyDetail'];

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
    queryFn: () => api.post<Analyzed>('/api/v2/analyze', { body }),
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
        ? api.post<Schemas['Created']>('/api/v2/strategies', { body })
        : api
            .post<Schemas['SavedVersion']>(`/api/v2/strategies/${String(id)}/versions`, {
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

export type VersionView = Schemas['VersionView'];
export type StrategyCard = Schemas['StrategyCard'];
export type StrategyDetail = Schemas['StrategyDetail'];
export type ImportPreview = Schemas['ImportPreview'];

export const useStrategyList = () =>
  useQuery({
    queryKey: ['strategies', 'v2'],
    queryFn: () => api.get<Schemas['StrategyList']>('/api/v2/strategies'),
  });

export const useStrategyDetail = (id: number) =>
  useQuery({
    queryKey: v2keys.strategy(id),
    queryFn: () => api.get<StrategyDetail>(`/api/v2/strategies/${String(id)}`),
  });

export const previewImport = (text: string) =>
  api.post<ImportPreview>('/api/v2/import/preview', { text });
export const acceptImport = (text: string) =>
  api.post<Schemas['Created']>('/api/v2/import/accept', { text });
export const importFile = (text: string) =>
  api.post<Schemas['Created']>('/api/v2/import/file', { text });
export const exportFile = (id: number) =>
  api.get<Schemas['ExportFile']>(`/api/v2/strategies/${String(id)}/file`);
export const copyText = (id: number) =>
  api.get<Schemas['CopyText']>(`/api/v2/strategies/${String(id)}/copytext`);
export const deleteStrategy = (id: number) =>
  api.delete<Schemas['OkOut']>(`/api/v2/strategies/${String(id)}`);

// ── 백테스트(T-32) ────────────────────────────────────────────────────────────

export type BacktestInput = Schemas['BacktestInput'];
export type BacktestTrade = Schemas['BacktestTrade'];
export type BacktestV2Result = Schemas['BacktestResult'];

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

export type PaperTrade = Schemas['PaperTrade'];
export type PaperRunV2 = Schemas['PaperRunV2'];
export type PaperPreview = Schemas['PaperPreview'];

export const usePaperRuns = () =>
  useQuery({
    queryKey: ['v2', 'paper'],
    queryFn: () => api.get<Schemas['PaperRuns']>('/api/v2/paper'),
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
