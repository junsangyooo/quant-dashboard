// 설정 v2 · 처음 실행 마법사가 쓰는 API(접속 · 텔레그램 · 데이터 · 업데이트).
import { useQuery } from '@tanstack/react-query';
import { api, request } from './client';
import type { components } from './types.gen';

type Schemas = components['schemas'];

// 서버 응답 모델(types.gen.ts)을 이름으로 가리켜요(손으로 쓴 API 타입 0 · P1-09)
export type AccessView = Schemas['AccessView'];
export type TelegramEvent = Schemas['TelegramEvent'];
export type TelegramView = Schemas['TelegramView'];
export type DataView = Schemas['DataView'];
export type DartConnect = Schemas['DartKey'];
export type About = Schemas['About'];
type RestoreOut = Schemas['RestoreOut'];

export const useAbout = () =>
  useQuery({ queryKey: ['about'], queryFn: () => api.get<About>('/api/about') });

export const settingsKeys = {
  access: ['access'] as const,
  telegram: ['telegram'] as const,
  data: ['data'] as const,
};

export const useAccess = () =>
  useQuery({ queryKey: settingsKeys.access, queryFn: () => api.get<AccessView>('/api/access') });

export const useTelegram = () =>
  useQuery({
    queryKey: settingsKeys.telegram,
    queryFn: () => api.get<TelegramView>('/api/telegram'),
  });

export const useDataView = () =>
  useQuery({ queryKey: settingsKeys.data, queryFn: () => api.get<DataView>('/api/data') });

export const setPlace = (place: 'server' | 'pc') =>
  api.put<AccessView>('/api/access/place', { place });

export const saveTelegramToken = (token: string) =>
  api.put<TelegramView>('/api/telegram', { token });
export const findTelegramChat = () => api.post<TelegramView>('/api/telegram/find-chat');
export const sendTelegramTest = () => api.post<TelegramView>('/api/telegram/test');
export const setTelegramEvent = (key: string, on: boolean) =>
  api.put<TelegramView>('/api/telegram/events', { key, on });

export const saveDartKey = (key: string) =>
  api.put<Schemas['ConnectView']>('/api/connect/dart', { key });

/** 내려받기: 응답을 파일로 저장해요(백업 · CSV). */
export async function download(path: string, fallbackName: string): Promise<void> {
  const res = await fetch(path, { credentials: 'same-origin' });
  if (!res.ok) throw new Error(`http-${String(res.status)}`);
  const blob = await res.blob();
  const cd = res.headers.get('content-disposition') ?? '';
  const name = /filename="([^"]+)"/.exec(cd)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

/** 복원: 파일 몸통을 그대로 보내요(비밀번호 창은 api/client가 띄워요). */
export async function restoreBackup(file: File): Promise<RestoreOut> {
  return request<RestoreOut>('POST', '/api/data/restore', {
    raw: await file.arrayBuffer(),
  });
}
