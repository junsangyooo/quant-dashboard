// 토스 연결(/api/connect): 설정 › 연결 · 처음 실행 마법사가 쓴다. api/mvp.ts에서 그대로 옮김(P1-03).
import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import { keys } from './query';
import type { components } from './types.gen';

type Schemas = components['schemas'];

// 서버 응답 모델(types.gen.ts)을 이름으로 가리켜요(손으로 쓴 API 타입 0 · P1-09)
export type CheckStep = Schemas['CheckStep'];
export type StepState = CheckStep['state'];
export type CheckResult = Schemas['CheckOk'] | Schemas['CheckFailed'];
export type ConnectView = Schemas['ConnectView'];

export const useConnect = () =>
  useQuery({ queryKey: keys.connect, queryFn: () => api.get<ConnectView>('/api/connect') });
