// 실전 운용(T-60 ~ T-64): /api/live/screen 한 번으로 자산 · 계획 · 기록 · 할 일 화면을 그려요.
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';

export interface LiveTodo {
  id: number;
  kind: string;
  severity: 'red' | 'yellow' | 'info';
  symbol: string | null;
  title: string;
  body: string | null;
  created_at: string;
}

export interface LiveAlert {
  id: number;
  at: string;
  live: number;
  kind: string;
  title: string;
  read: number;
}

export interface LiveHolding {
  sym: string;
  name: string;
  qty: number;
  avg: number;
  price: number;
  value: number;
  pnl: number;
  entry_d: string | null;
}

export interface PlanRow {
  sym: string;
  name: string;
  side: 'buy' | 'sell';
  reason: string[];
  close: number | null;
  kind?: string | null;
  qty: number;
  cap?: number;
  max?: number;
  est?: number;
}

export interface HistoryRow {
  d: string;
  symbol: string;
  name: string;
  side: string;
  price: number | null;
  qty: number;
  pnl: number | null;
  status: string;
  reason: string;
}

export interface WatchLevel {
  item: string;
  exec: string;
  trigger: number;
}

export interface LiveScreen {
  running: boolean;
  paused: boolean;
  halted: string | null;
  todos: LiveTodo[];
  alerts: LiveAlert[];
  names: Record<string, string>;
  account: {
    total: number;
    cash: number;
    holdings: { sym: string; name: string; qty: number; avg: number; price: number }[];
  } | null;
  id?: number;
  amount?: number;
  cash?: number;
  started_at?: string;
  account_tail?: string;
  manual?: string[];
  blocked?: Record<string, string>;
  next?: { judged: string; for_d: string; plans: unknown[] } | null;
  strategy?: { name: string; version_no: number };
  holdings?: LiveHolding[];
  eval?: number;
  equity?: number;
  curve?: [string, number][];
  plan_rows?: PlanRow[];
  history?: HistoryRow[];
  recent?: { d: string; sym: string; name: string; side: string; qty: number; price: number }[];
  realized?: number;
  trades?: number;
  orders_n?: number;
  watch?: { sym: string; name: string; levels: WatchLevel[]; price: number | null }[];
  last_check?: string | null;
}

export interface LivePreview {
  name: string;
  version_no: number;
  checks: { key: string; ok: boolean; tail?: string | null; place?: string | null }[];
  has_stop: boolean;
  ok: boolean;
}

export const liveKey = ['live-screen'] as const;

export const useLive = () =>
  useQuery({ queryKey: liveKey, queryFn: () => api.get<LiveScreen>('/api/live/screen') });

export const useLivePreview = (versionId: number) =>
  useQuery({
    queryKey: ['live-preview', versionId],
    queryFn: () => api.get<LivePreview>('/api/live/preview', { version_id: versionId }),
    enabled: versionId > 0,
  });

export function useLiveRefresh() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: liveKey });
}

export const liveApi = {
  start: (version_id: number, amount: number) =>
    api.post('/api/live/start', { version_id, amount }),
  pause: () => api.post('/api/live/pause'),
  resume: () => api.post('/api/live/resume'),
  end: () => api.post('/api/live/end'),
  sellAll: () => api.post('/api/live/sell-all'),
  todo: (id: number, what: 'match' | 'corp' | 'big-order' | 'unknown', body?: unknown) =>
    api.post(`/api/todos/${String(id)}/${what}`, body),
};
