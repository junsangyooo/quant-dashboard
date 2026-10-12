// React Query hooks: one per read endpoint, one per write. Screens never call fetch directly.
//
// - /api/shell polls every 60 s while the tab is visible and refetches when it comes back.
// - Ledger-scoped reads key on the resolved ledger (explicit `ledger` or the shell's mode), so
//   when another device switches the mode the keys change and every screen falls back to its
//   skeleton until the new ledger loads; a chip says what happened (SCR-HOME, node 1:50024).
// - A shell request with no response means '연결 안 됨'; screens keep their last data.
import {
  QueryClient,
  hashKey,
  onlineManager,
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from '@tanstack/react-query';
import { useSyncExternalStore } from 'react';
import { copy } from '../copy';
import type { HeaderStatus } from '../components/Chips';
import { formatTime } from '../lib/format';
import { NetworkError, api, shellPollMs } from './client';
import type {
  AccountId,
  AccountResponse,
  Breakdown,
  CancelRetryResponse,
  ChangePinRequest,
  DayResponse,
  DriftPeriod,
  HealthResponse,
  HistoryResponse,
  HomePeriod,
  HomeResponse,
  Ledger,
  LiveOffResponse,
  LiveOnRequest,
  LiveOnResponse,
  ModeResponse,
  NotificationsRequest,
  NotificationsResponse,
  PlanResponse,
  PushTestResponse,
  RuleDetailResponse,
  RulesListResponse,
  ShellResponse,
} from './types';

// ── keys ─────────────────────────────────────────────────────────────────────

export const queryKeys = {
  shell: ['shell'] as const,
  home: (ledger: Ledger | null, period?: HomePeriod) => ['home', ledger, period ?? null] as const,
  breakdown: (ledger: Ledger | null, period: HomePeriod, account?: AccountId) =>
    ['breakdown', ledger, period, account ?? null] as const,
  plan: (ledger: Ledger | null, drift?: DriftPeriod) => ['plan', ledger, drift ?? null] as const,
  history: (ledger: Ledger | null, year?: number) => ['history', ledger, year ?? null] as const,
  day: (date: string, ledger: Ledger | null) => ['day', date, ledger] as const,
  rules: ['rules'] as const,
  rule: (id: string, lane?: string) => ['rule', id, lane ?? null] as const,
  health: ['health'] as const,
  mode: ['mode'] as const,
  account: ['account'] as const,
};

// ── shell watcher: mode switches elsewhere, time of the last good load ───────

export interface ModeChange {
  /** When the server says the mode changed (falls back to the shell's `now`). */
  at: string;
  from: Ledger;
  to: Ledger;
}

interface WatchState {
  lastSeenMode: Ledger | null;
  change: ModeChange | null;
  /** Server time (`now`) of the last /api/shell answer. */
  lastLoadedAt: string | null;
}

const watch: WatchState = { lastSeenMode: null, change: null, lastLoadedAt: null };
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

const SHELL_HASH = hashKey(queryKeys.shell);
const notShell = { predicate: (q: { queryHash: string }) => q.queryHash !== SHELL_HASH };

function onShellLoaded(client: QueryClient, shell: ShellResponse): void {
  watch.lastLoadedAt = shell.now;
  if (watch.lastSeenMode !== null && shell.mode !== watch.lastSeenMode) {
    watch.change = {
      at: shell.modeChangedAt ?? shell.now,
      from: watch.lastSeenMode,
      to: shell.mode,
    };
    // Drop every other answer: numbers of the old ledger must not stay on screen.
    void client.resetQueries(notShell);
  }
  watch.lastSeenMode = shell.mode;
  emit();
}

/** Our own switch (실전 켜기/끄기) is not "another device". */
function ownModeChange(client: QueryClient, mode: Ledger): void {
  watch.lastSeenMode = mode;
  void client.resetQueries(notShell);
  void client.invalidateQueries({ queryKey: queryKeys.shell });
}

/** '[시각] 다른 기기에서 실전 → 모의투자로 바뀜' — null when nothing changed. */
export function useModeChange(): ModeChange | null {
  return useSyncExternalStore(
    subscribe,
    () => watch.change,
    () => null,
  );
}

/** The chip stays until the user moves to another page (AppShell clears it). */
export function dismissModeChange(): void {
  if (watch.change !== null) {
    watch.change = null;
    emit();
  }
}

/** Server time of the last successful /api/shell ('16:10 불러온 값 · 연결 안 됨'). */
export function useLastLoadedAt(): string | null {
  return useSyncExternalStore(
    subscribe,
    () => watch.lastLoadedAt,
    () => null,
  );
}

/** Forget what the watcher has seen (tests). */
export function resetDataLayer(): void {
  watch.lastSeenMode = null;
  watch.change = null;
  watch.lastLoadedAt = null;
  emit();
}

// ── client ───────────────────────────────────────────────────────────────────

function retryQuery(failureCount: number, error: unknown): boolean {
  // Contract errors (403, 404, 409 …) are answers, not hiccups; a dropped connection gets 2 more tries.
  return error instanceof NetworkError && failureCount < 2;
}

/** `retryDelayMs` replaces React Query's 1 s → 2 s back-off (tests use 0). */
export function createQueryClient(options: { retryDelayMs?: number } = {}): QueryClient {
  const { retryDelayMs } = options;
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: retryQuery,
        ...(retryDelayMs !== undefined ? { retryDelay: retryDelayMs } : {}),
        staleTime: 30_000,
        refetchOnWindowFocus: true,
      },
      mutations: { retry: false },
    },
  });
  client.getQueryCache().subscribe((event) => {
    if (
      event.type === 'updated' &&
      event.action.type === 'success' &&
      event.query.queryHash === SHELL_HASH
    ) {
      onShellLoaded(client, event.query.state.data as ShellResponse);
    }
  });
  return client;
}

// ── reads ────────────────────────────────────────────────────────────────────

/** Header data for every page; polls every 60 s, paused while the tab is hidden. */
export function useShell(): UseQueryResult<ShellResponse> {
  return useQuery({
    queryKey: queryKeys.shell,
    queryFn: ({ signal }) => api.get<ShellResponse>('/api/shell', undefined, signal),
    refetchInterval: shellPollMs(),
    refetchIntervalInBackground: false,
    staleTime: 0,
  });
}

/** The ledger a read is about: the explicit one (?ledger=) or the shell's current mode. */
export function useLedger(explicit?: Ledger): Ledger | null {
  const shell = useShell();
  return explicit ?? shell.data?.mode ?? null;
}

/** Server time of the current state (fixtures pin it); null until the shell loads. */
export function useNow(): string | null {
  return useShell().data?.now ?? null;
}

export function useHome(
  params: { ledger?: Ledger; period?: HomePeriod } = {},
): UseQueryResult<HomeResponse> {
  const ledger = useLedger(params.ledger);
  return useQuery({
    queryKey: queryKeys.home(ledger, params.period),
    queryFn: ({ signal }) =>
      api.get<HomeResponse>('/api/home', { ledger, period: params.period }, signal),
    enabled: ledger !== null,
  });
}

/** `account` asks for one account's change in its own currency (전체 when absent). */
export function useBreakdown(params: {
  ledger?: Ledger;
  period: HomePeriod;
  account?: AccountId | undefined;
  enabled?: boolean;
}): UseQueryResult<Breakdown> {
  const ledger = useLedger(params.ledger);
  return useQuery({
    queryKey: queryKeys.breakdown(ledger, params.period, params.account),
    queryFn: ({ signal }) =>
      api.get<Breakdown>(
        '/api/home/breakdown',
        { ledger, period: params.period, account: params.account },
        signal,
      ),
    enabled: ledger !== null && params.enabled !== false,
  });
}

export function usePlan(
  params: { ledger?: Ledger; drift?: DriftPeriod } = {},
): UseQueryResult<PlanResponse> {
  const ledger = useLedger(params.ledger);
  return useQuery({
    queryKey: queryKeys.plan(ledger, params.drift),
    queryFn: ({ signal }) =>
      api.get<PlanResponse>('/api/plan', { ledger, drift: params.drift }, signal),
    enabled: ledger !== null,
  });
}

export function useHistory(
  params: { ledger?: Ledger; year?: number } = {},
): UseQueryResult<HistoryResponse> {
  const ledger = useLedger(params.ledger);
  return useQuery({
    queryKey: queryKeys.history(ledger, params.year),
    queryFn: ({ signal }) =>
      api.get<HistoryResponse>('/api/history', { ledger, year: params.year }, signal),
    enabled: ledger !== null,
  });
}

/** `date` is a KST calendar key, YYYY-MM-DD. */
export function useDay(
  date: string,
  params: { ledger?: Ledger } = {},
): UseQueryResult<DayResponse> {
  const ledger = useLedger(params.ledger);
  return useQuery({
    queryKey: queryKeys.day(date, ledger),
    queryFn: ({ signal }) =>
      api.get<DayResponse>(`/api/day/${encodeURIComponent(date)}`, { ledger }, signal),
    enabled: ledger !== null,
  });
}

export function useRules(): UseQueryResult<RulesListResponse> {
  return useQuery({
    queryKey: queryKeys.rules,
    queryFn: ({ signal }) => api.get<RulesListResponse>('/api/rules', undefined, signal),
  });
}

export function useRule(
  id: string | undefined,
  params: { lane?: string } = {},
): UseQueryResult<RuleDetailResponse> {
  return useQuery({
    queryKey: queryKeys.rule(id ?? '', params.lane),
    queryFn: ({ signal }) =>
      api.get<RuleDetailResponse>(
        `/api/rules/${encodeURIComponent(id ?? '')}`,
        { lane: params.lane },
        signal,
      ),
    enabled: id !== undefined,
    // Switching the '흐름' lane of the same rule keeps the last lane on screen until the new one
    // arrives (no skeleton flash); another rule starts from its skeleton.
    placeholderData: (previous) => (previous?.rule.id === id ? previous : undefined),
  });
}

export function useHealth(): UseQueryResult<HealthResponse> {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => api.get<HealthResponse>('/api/health', undefined, signal),
  });
}

export function useMode(): UseQueryResult<ModeResponse> {
  return useQuery({
    queryKey: queryKeys.mode,
    queryFn: ({ signal }) => api.get<ModeResponse>('/api/mode', undefined, signal),
  });
}

export function useAccount(): UseQueryResult<AccountResponse> {
  return useQuery({
    queryKey: queryKeys.account,
    queryFn: ({ signal }) => api.get<AccountResponse>('/api/account', undefined, signal),
  });
}

// ── connection and header status ─────────────────────────────────────────────

/** online · offline ('연결 안 됨': no answer) · unknown ('확인 불가': the shell answered with an error). */
export type Connection = 'online' | 'offline' | 'unknown';

function subscribeOnline(listener: () => void): () => void {
  return onlineManager.subscribe(listener);
}

export function useConnection(): Connection {
  const online = useSyncExternalStore(
    subscribeOnline,
    () => onlineManager.isOnline(),
    () => true,
  );
  const shell = useShell();
  if (!online) return 'offline';
  if (shell.isError) return shell.error instanceof NetworkError ? 'offline' : 'unknown';
  return 'online';
}

export interface HeaderStatusView {
  status: HeaderStatus;
  label: string;
}

/** Header chip (Figma 칩/헤더 상태): null while the first shell answer is on its way. */
export function headerStatusView(
  shell: ShellResponse | undefined,
  connection: Connection,
): HeaderStatusView | null {
  if (connection === 'offline') return { status: 'unknown', label: copy.headerStatus.offline };
  if (connection === 'unknown') return { status: 'unknown', label: copy.headerStatus.unknown };
  if (!shell) return null;
  const s = shell.status;
  switch (s.kind) {
    case 'ok':
      return { status: 'ok', label: copy.headerStatus.ok(formatTime(s.lastCheckAt)) };
    case 'before-first':
      return { status: 'ok', label: copy.headerStatus.beforeFirstCheck };
    case 'check':
      return { status: 'check', label: copy.headerStatus.check(s.count) };
    case 'check-failed':
      return { status: 'error', label: copy.headerStatus.checkFailed };
    case 'todo':
      return { status: 'error', label: copy.headerStatus.todo(s.count) };
    case 'cancel-failed':
      return { status: 'error', label: copy.headerStatus.notCancelled(s.count) };
  }
}

export function useHeaderStatus(): HeaderStatusView | null {
  const shell = useShell();
  const connection = useConnection();
  return headerStatusView(shell.data, connection);
}

// ── writes ───────────────────────────────────────────────────────────────────

/** POST /api/auth/pin — 403 'pin' {remaining} or 'locked' {until, scope} arrive as ApiError. */
export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (pin: string) => api.post('/api/auth/pin', { pin }),
    onSuccess: () => {
      resetDataLayer();
      void client.invalidateQueries();
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post('/api/auth/logout'),
    onSuccess: () => {
      resetDataLayer();
      client.clear();
    },
  });
}

export function useLogoutOthers() {
  return useMutation({ mutationFn: () => api.post('/api/auth/logout-others') });
}

/** 403 'current-pin' when the current PIN is wrong. */
export function useChangePin() {
  return useMutation({
    mutationFn: (body: ChangePinRequest) => api.post('/api/account/pin', body),
  });
}

/** 409 'preview-changed' {preview} · 'blocked' · 'in-progress' arrive as ApiError. */
export function useTurnLiveOn() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Omit<LiveOnRequest, 'confirm'>) =>
      api.post<LiveOnResponse>('/api/mode/live', { ...body, confirm: true }),
    onSuccess: (data) => {
      ownModeChange(client, data.mode);
    },
  });
}

export function useTurnLiveOff() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<LiveOffResponse>('/api/mode/paper'),
    onSuccess: (data) => {
      ownModeChange(client, data.mode);
    },
  });
}

export function useCancelRetry() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<CancelRetryResponse>('/api/mode/cancel-retry'),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.mode });
      void client.invalidateQueries({ queryKey: queryKeys.shell });
    },
  });
}

export function useSaveNotifications() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: NotificationsRequest) =>
      api.put<NotificationsResponse>('/api/account/notifications', body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.account });
    },
  });
}

export function usePushSubscribe() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (subscription: PushSubscriptionJSON) =>
      api.post('/api/account/push', { subscription }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.account });
    },
  });
}

/** DELETE /api/account/push — ends this device's subscription (501 until web push, phase 3). */
export function usePushUnsubscribe() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.delete('/api/account/push'),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.account });
    },
  });
}

export function usePushTest() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<PushTestResponse>('/api/account/push/test'),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: queryKeys.account });
    },
  });
}
