// 토스 연결(/api/connect): 설정 › 연결 · 처음 실행 마법사가 쓴다. api/mvp.ts에서 그대로 옮김(P1-03).
import { useQuery } from '@tanstack/react-query';
import { api } from './client';
import { keys } from './query';

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

export const useConnect = () =>
  useQuery({ queryKey: keys.connect, queryFn: () => api.get<ConnectView>('/api/connect') });
