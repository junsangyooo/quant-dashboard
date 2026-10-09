// SCR-HEALTH 작동 (Figma 1:62685 · 1:62952 · 1:63248 · 1:63518 · 1:63806): what is how old, where
// something stopped, and whether it retries by itself or needs a hand.
// 390: ‹ 작동 → 종합 → 할 일 → 자료별 → 최근 14일. 1440: left 4 of 12 (종합 · 할 일 · 14일),
// right 8 of 12 (자료별).
import clsx from 'clsx';
import {
  CircleCheck,
  CircleHelp,
  CircleX,
  Clock,
  TriangleAlert,
  type LucideIcon,
} from 'lucide-react';
import { copy } from '../../copy';
import { healthCopy as t } from '../../copy/health';
import { useHealth, useLastLoadedAt, useNow, useShell } from '../../api/queries';
import type { ShellResponse } from '../../api/types';
import { Button } from '../../components/Buttons';
import { InfoChip, SignalChip } from '../../components/Chips';
import { Skeleton, SkeletonBlock } from '../../components/State';
import { formatDateTime, formatTime } from '../../lib/format';
import { PageTitle } from '../../shell/PageTitle';
import { pageTitle, useDocumentTitle } from '../../shell/page';
import { RecentCard } from './RecentCard';
import { SourcesCard } from './SourcesCard';
import { TodoCard } from './TodoCard';
import { summaryView, unknownView, type SummaryTone, type SummaryView } from './text';
import styles from './Health.module.css';

const TONE_ICON: Record<SummaryTone, LucideIcon> = {
  ok: CircleCheck,
  check: TriangleAlert,
  error: CircleX,
  unknown: CircleHelp,
  wait: Clock,
};

function Summary({
  view,
  onRetry,
  retrying,
}: {
  view: SummaryView;
  onRetry?: (() => void) | undefined;
  retrying?: boolean | undefined;
}) {
  const Icon = TONE_ICON[view.tone];
  return (
    <section className={clsx(styles.summary, styles.areaSummary)} aria-labelledby="health-summary">
      <div className={styles.summaryHead}>
        <Icon size={40} className={styles[`tone-${view.tone}`]} aria-hidden />
        <div className={styles.summaryText}>
          <h2 id="health-summary" className="t-title">
            {view.label}
          </h2>
          <p className={clsx('t-caption', styles.muted)}>{view.line}</p>
        </div>
      </div>
      {view.chips.length > 0 ? (
        <div className={styles.chips}>
          {view.chips.map((chip) =>
            chip.kind === 'info' ? (
              <InfoChip key={chip.label}>{chip.label}</InfoChip>
            ) : (
              <SignalChip key={chip.label} kind={chip.kind}>
                {chip.label}
              </SignalChip>
            ),
          )}
        </div>
      ) : null}
      {onRetry ? (
        <Button kind="default" block className={styles.retry} onClick={onRetry} disabled={retrying}>
          {copy.state.retry}
        </Button>
      ) : null}
    </section>
  );
}

function SummarySkeleton() {
  return (
    <section className={clsx(styles.summary, styles.areaSummary)} aria-busy="true">
      <div className={styles.summaryHead}>
        <SkeletonBlock height={40} className={styles.iconSkeleton} />
        <div className={styles.summaryText}>
          <Skeleton text="title" width={64} />
          <Skeleton text="caption" width={140} />
        </div>
      </div>
      <Skeleton text="caption" width={260} />
    </section>
  );
}

/** The last time anything said how the checks went: the last health answer, else the shell. */
function lastKnownCheck(lastCheckAt: string | null | undefined, shell: ShellResponse | undefined) {
  if (lastCheckAt) return lastCheckAt;
  const s = shell?.status;
  if (s?.kind === 'ok') return s.lastCheckAt;
  if (s?.kind === 'check-failed') return s.at;
  return null;
}

export function HealthScreen() {
  useDocumentTitle(pageTitle('health'));
  const q = useHealth();
  const shell = useShell();
  const now = useNow();
  const loadedAt = useLastLoadedAt();

  const withTodos = !q.isError && (q.data?.todos.length ?? 0) > 0;
  let body;
  if (q.isPending) {
    body = (
      <>
        <SummarySkeleton />
        <div className={styles.areaSources}>
          <SkeletonBlock height={480} />
        </div>
        <div className={styles.areaRecent}>
          <SkeletonBlock height={300} />
        </div>
      </>
    );
  } else if (q.isError) {
    // '확인 불가': never draw '정상' from old numbers; the sections below show '—'.
    const attempt = formatTime(new Date(q.errorUpdatedAt));
    const last = lastKnownCheck(q.data?.summary.lastCheckAt, shell.data);
    body = (
      <>
        <Summary
          view={unknownView(attempt, last ? formatDateTime(last) : null)}
          onRetry={() => void q.refetch()}
          retrying={q.isFetching}
        />
        <SourcesCard sources={q.data?.sources ?? null} now={now} unknown />
        <RecentCard days={null} lastRun={null} />
      </>
    );
  } else {
    const h = q.data;
    body = (
      <>
        <Summary view={summaryView(h, now ?? loadedAt)} />
        {h.todos.length > 0 ? (
          <section className={clsx(styles.todos, styles.areaTodos)} aria-labelledby="health-todos">
            <h2 id="health-todos" className="sr-only">
              {t.todo.title}
            </h2>
            {h.todos.map((todo) => (
              <TodoCard key={todo.id} todo={todo} now={now} />
            ))}
          </section>
        ) : null}
        <SourcesCard sources={h.sources} now={now} />
        <RecentCard days={h.recent14} lastRun={h.lastRun} />
      </>
    );
  }

  return (
    <div className={styles.screen}>
      <PageTitle>{copy.pages.health}</PageTitle>
      <div className={clsx(styles.grid, withTodos && styles.withTodos)}>{body}</div>
    </div>
  );
}
