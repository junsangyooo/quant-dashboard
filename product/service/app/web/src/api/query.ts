// React Query 바탕: 쿼리 키 · 클라이언트(staleTime 5초 · 재시도 규칙) · 쓰기 훅. api/mvp.ts에서 그대로 옮김(P1-03).
import { QueryClient, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, isApiError } from './client';

export const keys = {
  state: ['state'] as const,
  connect: ['connect'] as const,
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
