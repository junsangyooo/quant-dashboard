// 실전 운용(T-60 ~ T-64): /api/live/screen 한 번으로 자산 · 계획 · 기록 · 할 일 화면을 그려요.
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';
import type { components } from './types.gen';

type Schemas = components['schemas'];

// 서버 응답 모델(types.gen.ts)을 이름으로 가리켜요(손으로 쓴 API 타입 0 · P1-09)
export type LiveTodo = Schemas['LiveTodo'];
export type LiveAlert = Schemas['LiveAlert'];
export type LiveHolding = Schemas['LiveHolding'];
export type PlanRow = Schemas['PlanRow'];
export type HistoryRow = Schemas['HistoryRow'];
export type WatchLevel = Schemas['WatchLevel'];
export type LiveScreen = Schemas['LiveScreen'];
export type LivePreview = Schemas['LivePreview'];

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
