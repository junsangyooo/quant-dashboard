// SCR-DAY 그날 (Figma 1:59915 · 1:60076 · 1:60239): ‹ date › with the previous and next event
// dates · 예시 · × → 그날 자산 and the change from the day before → event cards → 그날 확인 → 기준.
// - variant 'sheet' (below 1100px): a full-height modal sheet over everything, header included;
//   focus stays inside and Escape closes it.
// - variant 'panel' (1100px up): a right-side panel over the 기록 page's right column; the page
//   stays usable (rows and markers change the day) and Escape closes it.
import clsx from 'clsx';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import {
  useEffect,
  useId,
  useRef,
  type KeyboardEvent,
  type MouseEvent,
  type ReactNode,
} from 'react';
import { Link } from 'react-router';
import { useDay } from '../../api/queries';
import type { DayEvent, DayResponse, Ledger } from '../../api/types';
import { ErrorBlock, ExampleChip, Skeleton, SkeletonBlock } from '../../components/State';
import { copy } from '../../copy';
import { dayCopy as dc } from '../../copy/day';
import { formatKrw, formatMonthDay, formatMonthDayWeekday } from '../../lib/format';
import { ChangeLine } from '../History/AssetCard';
import { ruleName } from '../History/historyModel';
import { CheckCard } from './CheckCard';
import { basisParts, prevNextLine } from './dayModel';
import { EventCard } from './EventCards';
import styles from './Day.module.css';

export interface DayPanelProps {
  date: string;
  /** ?ledger= when the other ledger is open (else the current mode's ledger). */
  ledger: Ledger | null;
  /** The 기록 search (ledger · filters) carried by ‹ ›. */
  search: string;
  /** Escape and a plain click on ×: back to where the panel was opened, else to `closeHref`. */
  onClose: () => void;
  /** Where × leads (기록 with the same search); also the target of a new-tab click. */
  closeHref: string;
  variant: 'sheet' | 'panel';
}

function plainClick(e: MouseEvent): boolean {
  return e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey;
}

function NavButton({
  date,
  dir,
  search,
}: {
  date: string | null;
  dir: 'prev' | 'next';
  search: string;
}) {
  const Icon = dir === 'prev' ? ChevronLeft : ChevronRight;
  if (!date) {
    return (
      <button
        type="button"
        className={styles.navButton}
        disabled
        aria-label={dir === 'prev' ? dc.noPrev : dc.noNext}
      >
        <Icon size={20} aria-hidden />
      </button>
    );
  }
  const label =
    dir === 'prev' ? dc.prevButton(formatMonthDay(date)) : dc.nextButton(formatMonthDay(date));
  return (
    <Link
      to={`/day/${date}${search}`}
      replace
      preventScrollReset
      className={styles.navButton}
      aria-label={label}
    >
      <Icon size={20} aria-hidden />
    </Link>
  );
}

/** '진행 중 단계 보기' while a rebalance still has a stage to go (기획 §5 SCR-DAY 행동). */
function showsPlanLink(event: DayEvent): boolean {
  if (event.kind === 'in-progress') return true;
  if (event.kind !== 'partial-failed') return false;
  return event.stages.some((s) =>
    s.orders.some((o) => o.status === 'failed' && o.failure?.retryAt && !o.retried),
  );
}

function DayBody({
  data,
  ruleNameOf,
}: {
  data: DayResponse;
  ruleNameOf: (id: string) => string | null;
}) {
  // The check names its rule (CONTRACT check.rule); an older answer falls back to the events.
  const checkRule = data.check.rule
    ? ruleName(data.check.rule)
    : data.check.ruleId !== undefined
      ? ruleNameOf(data.check.ruleId)
      : null;
  return (
    <>
      <section className={styles.total} aria-label={dc.total(copy.mode[data.ledger])}>
        <p className={clsx('t-caption', styles.muted)}>{dc.total(copy.mode[data.ledger])}</p>
        <p className="t-title">{formatKrw(data.total)}</p>
        <p className={styles.changeRow}>
          {data.change ? (
            <ChangeLine amount={data.change.amount} pct={data.change.pct} />
          ) : (
            <span className={clsx('t-label', styles.muted)}>{dc.noChange}</span>
          )}
          <span className={clsx('t-caption', styles.muted)}>{dc.vsPrevDay}</span>
        </p>
      </section>
      {data.events.map((event, i) => (
        <EventCard key={`${event.kind}-${String(i)}`} event={event} toPlan={showsPlanLink(event)} />
      ))}
      <CheckCard check={data.check} ruleName={checkRule} />
      <p className={clsx('t-caption', styles.muted)}>{dc.basis(basisParts(data.basis))}</p>
    </>
  );
}

function DaySkeleton() {
  return (
    <>
      <section className={styles.total}>
        <Skeleton text="caption" width={110} />
        <Skeleton text="title" width={150} />
        <Skeleton text="label" width={190} />
      </section>
      <SkeletonBlock height={320} />
      <SkeletonBlock height={148} />
      <Skeleton text="caption" width={300} />
    </>
  );
}

export function DayPanel({ date, ledger, search, onClose, closeHref, variant }: DayPanelProps) {
  const q = useDay(date, ledger ? { ledger } : {});
  const headingId = useId();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);

  // The sheet is modal: the page behind is inert and Escape cancels (handled below).
  useEffect(() => {
    if (variant !== 'sheet') return;
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) {
      dialog.showModal();
      // The date takes the first focus (not the ‹ link the dialog would pick).
      headingRef.current?.focus();
    }
    return () => {
      if (dialog?.open) dialog.close();
    };
  }, [variant]);

  // The panel takes focus when it opens (after the shell has moved focus to <main>).
  useEffect(() => {
    if (variant !== 'panel') return;
    const timer = window.setTimeout(() => {
      headingRef.current?.focus({ preventScroll: true });
    }, 0);
    return () => {
      window.clearTimeout(timer);
    };
  }, [variant]);

  const data = q.data;
  const prev = data?.prev ?? null;
  const next = data?.next ?? null;
  const line = data ? prevNextLine(prev, next) : null;
  const ruleNameOf = (id: string): string | null => {
    const fromEvents = data?.events.find(
      (e): e is Extract<DayEvent, { rule: unknown }> => 'rule' in e && e.rule.id === id,
    );
    return fromEvents ? ruleName(fromEvents.rule) : null;
  };
  const Heading = variant === 'sheet' ? 'h1' : 'h2';

  const content: ReactNode = (
    <>
      <div className={styles.head}>
        <NavButton date={prev} dir="prev" search={search} />
        <div className={styles.dateBlock}>
          {/* The heading takes the first focus of the sheet and of the panel when it opens. */}
          <Heading
            id={headingId}
            ref={headingRef}
            tabIndex={-1}
            className={clsx('t-heading-1', styles.dateHeading)}
          >
            {formatMonthDayWeekday(date)}
          </Heading>
          {line ? <p className={clsx('t-micro', styles.muted)}>{line}</p> : null}
        </div>
        <NavButton date={next} dir="next" search={search} />
        <span className={styles.grow} />
        <ExampleChip show={data?.example ?? false} />
        <Link
          to={closeHref}
          replace
          className={styles.closeButton}
          aria-label={copy.close}
          onClick={(e) => {
            if (!plainClick(e)) return;
            e.preventDefault();
            onClose();
          }}
        >
          <X size={20} aria-hidden />
        </Link>
      </div>
      <div className={styles.body}>
        {q.isPending ? (
          <DaySkeleton />
        ) : !data ? (
          <ErrorBlock
            message={copy.state.errors.day}
            onRetry={() => void q.refetch()}
            retrying={q.isFetching}
          />
        ) : (
          <DayBody data={data} ruleNameOf={ruleNameOf} />
        )}
      </div>
    </>
  );

  if (variant === 'sheet') {
    return (
      <dialog
        ref={dialogRef}
        className={styles.sheet}
        aria-labelledby={headingId}
        aria-busy={q.isPending || undefined}
        onCancel={(e) => {
          e.preventDefault();
          onClose();
        }}
      >
        {content}
      </dialog>
    );
  }
  return (
    // Escape closes the panel, as it does the sheet; the panel holds real controls.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <aside
      className={styles.panel}
      aria-labelledby={headingId}
      aria-busy={q.isPending || undefined}
      onKeyDown={(e: KeyboardEvent<HTMLElement>) => {
        if (e.key === 'Escape') {
          e.preventDefault();
          onClose();
        }
      }}
    >
      {content}
    </aside>
  );
}
