// SCR-MODE sections: 모의투자 성적, 켜기 전 점검, 첫 주문 미리보기, 취소 안 된 주문.
import clsx from 'clsx';
import { Fragment, useId } from 'react';
import {
  ArrowDown,
  ArrowLeftRight,
  ChevronDown,
  CircleMinus,
  CirclePlus,
  type LucideIcon,
} from 'lucide-react';
import { modeCopy as t } from '../../copy/mode';
import type { ModeResponse, Order } from '../../api/types';
import { Button, LinkButton } from '../../components/Buttons';
import { InfoChip, SignalChip } from '../../components/Chips';
import { CheckRow, OrderRow } from '../../components/Rows';
import { CompositionBar, type SegmentTone } from '../../charts/CompositionBar';
import {
  formatKrwSigned,
  formatMonthDay,
  formatPercent,
  formatPercentSigned,
  formatTime,
  pnlDirection,
} from '../../lib/format';
import {
  basisChips,
  cancelFailedRow,
  currentItems,
  firstCheckText,
  notComputableLines,
  outsideLine,
  preflightRow,
  shortName,
  stageView,
  visibleStages,
  type OkPreview,
  type Preview,
} from './text';
import styles from './Mode.module.css';

type Mode = ModeResponse;

// ── 모의투자 성적 ─────────────────────────────────────────────────────────────

export function PerformanceCard({
  performance: p,
  firstCheckAt,
  showLink,
}: {
  performance: Mode['performance'];
  /** Shown when the paper ledger has no check yet ('첫 확인 7/1(수) 08:30'). */
  firstCheckAt: string | null;
  /** The two-ledger card carries both links; otherwise this card links to the paper 기록. */
  showLink: boolean;
}) {
  const titleId = useId();
  const empty = p.checks === 0;
  const direction = p.ret ? pnlDirection(p.ret.pct, 2) : 'flat';
  const tiles = [
    {
      key: 'checks',
      value: t.performance.times(p.checks),
      label: t.performance.checks,
      alert: false,
    },
    {
      key: 'rebalances',
      value: t.performance.times(p.rebalances),
      label: t.performance.rebalances,
      alert: false,
    },
    {
      key: 'failures',
      value: t.performance.times(p.failures),
      label: t.performance.failures,
      alert: p.failures > 0,
    },
    {
      key: 'fills',
      value: t.performance.items(p.paperFills),
      label: t.performance.fills,
      alert: false,
    },
  ];
  return (
    <section className={clsx(styles.card, styles.subtle)} aria-labelledby={titleId}>
      <div className={styles.cardHead}>
        <h2 id={titleId} className="t-heading-1">
          {t.performance.title}
        </h2>
        <span className={clsx('t-caption', styles.muted)}>
          {t.performance.since(formatMonthDay(p.since))}
        </span>
      </div>
      {empty ? (
        <p className={clsx('t-body', styles.muted)}>
          {firstCheckAt
            ? t.performance.empty(firstCheckText(firstCheckAt))
            : t.performance.emptyNoTime}
        </p>
      ) : (
        <>
          <p className={clsx('t-label', styles.muted)}>{t.performance.ops}</p>
          <ul className={styles.tiles}>
            {tiles.map((tile) => (
              <li key={tile.key} className={styles.tile}>
                <span className={clsx('t-heading-1', tile.alert && styles.error)}>
                  {tile.value}
                </span>
                <span className={clsx('t-caption', styles.muted)}>{tile.label}</span>
              </li>
            ))}
          </ul>
          <p className={clsx('t-label', styles.muted)}>{t.performance.ret}</p>
          {p.ret ? (
            <div className={styles.retBlock}>
              <p className={clsx('t-title', styles[`pnl-${direction}`])}>
                {direction === 'gain' ? (
                  <>
                    <span className={styles.triangle} aria-hidden>
                      ▲
                    </span>
                    <span className="sr-only">{t.performance.up}</span>
                  </>
                ) : direction === 'loss' ? (
                  <>
                    <span className={styles.triangle} aria-hidden>
                      ▼
                    </span>
                    <span className="sr-only">{t.performance.down}</span>
                  </>
                ) : null}
                {formatPercentSigned(p.ret.pct, 2)}
              </p>
              <div className={styles.chips}>
                <InfoChip>{formatKrwSigned(p.ret.amount)}</InfoChip>
                {p.baselinePct !== null ? (
                  <InfoChip>
                    {t.performance.baseline(formatPercentSigned(p.baselinePct, 2))}
                  </InfoChip>
                ) : null}
              </div>
              <p className={clsx('t-caption', styles.muted)}>{t.performance.note}</p>
            </div>
          ) : (
            <div className={styles.retBlock}>
              <SignalChip kind="warn">{t.performance.short}</SignalChip>
              <p className={clsx('t-caption', styles.muted)}>{t.performance.shortNote(p.checks)}</p>
            </div>
          )}
        </>
      )}
      {showLink ? (
        <LinkButton to="/history?ledger=paper" className={styles.alignStart}>
          {t.performance.history}
        </LinkButton>
      ) : null}
    </section>
  );
}

// ── 켜기 전 점검 ─────────────────────────────────────────────────────────────

export function PreflightSection({
  preflight,
  now,
}: {
  preflight: NonNullable<Mode['preflight']>;
  now: string | null;
}) {
  const titleId = useId();
  return (
    <section className={styles.preflight} aria-labelledby={titleId}>
      <h2 id={titleId} className="t-heading-1">
        {t.preflight.title}
      </h2>
      <ul className={styles.checkList}>
        {preflight.map((item) => {
          const row = preflightRow(item, now);
          const to =
            row.state === 'blocked'
              ? '/health'
              : row.state === 'warn'
                ? item.id === 'push'
                  ? '/account#notifications'
                  : '/health'
                : undefined;
          return (
            <li key={item.id}>
              <CheckRow state={row.state} name={row.name} description={row.description} to={to} />
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ── 첫 주문 미리보기 ─────────────────────────────────────────────────────────

const CAT: readonly SegmentTone[] = ['cat-1', 'cat-2', 'cat-3', 'cat-4', 'cat-5'];

const STAGE_ICON: Record<'sell' | 'fx' | 'buy', LucideIcon> = {
  sell: CircleMinus,
  fx: ArrowLeftRight,
  buy: CirclePlus,
};

function PreviewOk({ preview: p, now }: { preview: OkPreview; now: string | null }) {
  const tone = (id: string): SegmentTone => {
    const i = p.target.findIndex((x) => x.instrument.id === id);
    return i === -1 ? 'cash' : (CAT[i % CAT.length] ?? 'cash');
  };
  const items = currentItems(p);
  const stages = visibleStages(p.stages);
  return (
    <>
      <p className={clsx('t-caption', styles.muted)}>{t.preview.now(items.join(' · '))}</p>
      <CompositionBar
        label={t.preview.nowBar(items.join(' · '))}
        segments={p.current.map((c, i) => ({
          key: `${c.label}-${c.instrument?.id ?? String(i)}`,
          value: c.krw,
          tone: c.label === 'holding' && c.instrument ? tone(c.instrument.id) : 'cash',
        }))}
      />
      <div className={styles.arrow} aria-hidden>
        <ArrowDown size={20} />
      </div>
      <p className={clsx('t-caption', styles.muted)}>{t.preview.target}</p>
      <CompositionBar
        label={t.preview.targetBar(
          p.target.map((x) => `${x.instrument.name} ${formatPercent(x.pct)}`).join(' · '),
        )}
        segments={p.target.map((x) => ({
          key: x.instrument.id,
          value: x.pct,
          tone: tone(x.instrument.id),
        }))}
      />
      <ul className={styles.targetLegend}>
        {p.target.map((x) => (
          <li key={x.instrument.id} className={styles.legendItem}>
            <span
              className={clsx(styles.legendDot, styles[`fill-${tone(x.instrument.id)}`])}
              aria-hidden
            />
            <span className={clsx('t-caption', styles.muted)}>{shortName(x.instrument)}</span>
          </li>
        ))}
      </ul>
      {stages.length > 0 ? (
        <ol className={styles.legs}>
          {stages.map((stage, i) => {
            const view = stageView(stage, now);
            const Icon = STAGE_ICON[stage.kind];
            return (
              <Fragment key={stage.kind}>
                {i > 0 ? (
                  <li className={styles.legArrow} aria-hidden>
                    <ChevronDown size={16} />
                  </li>
                ) : null}
                <li className={styles.leg}>
                  <div className={styles.legHead}>
                    <Icon size={18} className={styles.accent} aria-hidden />
                    <span className={clsx('t-label', styles.legLabel)}>{view.label}</span>
                    <span className={clsx('t-caption', styles.muted)}>{view.time}</span>
                  </div>
                  <p className="t-body">
                    {view.body.map((line, j) => (
                      <Fragment key={line}>
                        {j > 0 ? <br /> : null}
                        {line}
                      </Fragment>
                    ))}
                  </p>
                  <p className={styles.legAmount}>
                    <span className="t-body-strong">{view.amount}</span>
                    {view.note ? (
                      <span className={clsx('t-caption', styles.muted)}>{view.note}</span>
                    ) : null}
                  </p>
                </li>
              </Fragment>
            );
          })}
        </ol>
      ) : null}
      <div className={styles.chips}>
        {basisChips(p, now).map((chip) => (
          <InfoChip key={chip}>{chip}</InfoChip>
        ))}
      </div>
      {p.outside.map((o) => (
        <p key={o.instrument.id} className={clsx('t-caption', styles.muted)}>
          {outsideLine(o)}
        </p>
      ))}
    </>
  );
}

export function PreviewCard({
  preview,
  preflight,
  changedAt,
  now,
}: {
  preview: Preview;
  preflight: Mode['preflight'];
  /** Set after 409 preview-changed: '16:10 다시 계산 · 금액 바뀜'. */
  changedAt: string | null;
  now: string | null;
}) {
  const titleId = useId();
  return (
    <section className={clsx(styles.card, styles.subtle)} aria-labelledby={titleId}>
      <div className={styles.cardHead}>
        <h2 id={titleId} className="t-heading-1">
          {t.preview.title}
        </h2>
        <InfoChip>{t.preview.account}</InfoChip>
      </div>
      {changedAt ? (
        <div role="status">
          <SignalChip kind="warn">{t.preview.changed(formatTime(changedAt))}</SignalChip>
        </div>
      ) : null}
      {preview.kind === 'ok' ? (
        <PreviewOk preview={preview} now={now} />
      ) : (
        <>
          <SignalChip kind="warn" className={styles.alignStart}>
            {notComputableLines(preview, preflight).chip}
          </SignalChip>
          <p className={clsx('t-caption', styles.muted)}>
            {notComputableLines(preview, preflight).note}
          </p>
        </>
      )}
    </section>
  );
}

// ── 취소 안 된 주문 ──────────────────────────────────────────────────────────

export function CancelFailedCard({
  orders,
  onRetry,
  retrying,
  failed,
}: {
  orders: readonly Order[];
  onRetry: () => void;
  retrying: boolean;
  failed: boolean;
}) {
  const titleId = useId();
  const first = orders[0];
  return (
    <section className={styles.cancelFailed} aria-labelledby={titleId}>
      <h2 id={titleId} className={clsx('t-body-strong', styles.error)}>
        {t.cancelFailed.title}
      </h2>
      <ul className={styles.cancelList}>
        {orders.map((o) => (
          <li key={o.id}>
            <OrderRow
              state="failed"
              stateLabel={t.cancelFailed.stateLabel}
              time={t.cancelFailed.waiting(formatTime(o.at))}
            >
              {cancelFailedRow(o)}
            </OrderRow>
          </li>
        ))}
      </ul>
      {first ? (
        <p className={clsx('t-caption', styles.muted)}>
          {t.cancelFailed.warn(formatTime(first.at))}
        </p>
      ) : null}
      <Button kind="default" className={styles.wide} onClick={onRetry} disabled={retrying}>
        {retrying ? t.cancelFailed.retrying : t.cancelFailed.retry}
      </Button>
      {failed ? (
        <p className={clsx('t-caption', styles.error)} role="status">
          {t.cancelFailed.retryFailed}
        </p>
      ) : null}
    </section>
  );
}
