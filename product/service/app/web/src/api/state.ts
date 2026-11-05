// 앱 상태(/api/state): 문 단속(비밀번호 만들기 · 로그인)과 머리가 쓴다. api/mvp.ts에서 그대로 옮김(P1-03).
import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import { keys } from './query';
import type { components } from './types.gen';

/** 서버 응답 모델 `AppState`(types.gen.ts) · `restarted`: 서버가 다시 켜진 뒤 아직 한 번도 로그인하지 않았다('앱을 다시 켰어요' 안내). */
export type AppState = components['schemas']['AppState'];

export const useAppState = () =>
  useQuery({ queryKey: keys.state, queryFn: () => api.get<AppState>('/api/state') });
