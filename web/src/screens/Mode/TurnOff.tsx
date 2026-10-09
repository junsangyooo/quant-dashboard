// 실전 끄기 (Figma 1:64317 · 1:64669): a red wide button and a line; it opens a centred modal with
// the orders that will be cancelled, the cash that stays, two chips and [취소][끄기]. No PIN —
// a valid session is enough (인계 7), also while PIN entry is locked.
import clsx from 'clsx';
import { useState, type Ref } from 'react';
import { Hourglass } from 'lucide-react';
import { modeCopy as t } from '../../copy/mode';
import { useHome, usePlan, useTurnLiveOff } from '../../api/queries';
import type { Currency, Order } from '../../api/types';
import { Button } from '../../components/Buttons';
import { InfoChip } from '../../components/Chips';
import { ConfirmModal } from '../../components/ConfirmModal';
import { Skeleton } from '../../components/State';
import { cancelBody, cancelHead, cashStaysLine } from './text';
import styles from './Mode.module.css';

/** Orders the pipeline sent that have not filled: what turning live off cancels. */
function pendingOrders(
  stages: readonly { orders: readonly Order[] }[] | null | undefined,
): Order[] {
  return (stages ?? []).flatMap((s) => s.orders.filter((o) => o.status === 'pending'));
}

function OffDetails({ now, failed }: { now: string | null; failed: boolean }) {
  const plan = usePlan({ ledger: 'live' });
  const home = useHome({ ledger: 'live' });
  const orders = pendingOrders(plan.data?.schedule.now?.stages);
  const currencies = new Set<Currency>(
    orders.filter((o) => o.side === 'buy').map((o) => o.instrument?.currency ?? 'KRW'),
  );
  const cashRows = (home.data?.composition.groups ?? []).flatMap((g) =>
    g.rows.filter((r) => r.kind === 'cash'),
  );
  const usd = cashRows
    .filter((r) => r.cash?.currency === 'USD')
    .reduce((s, r) => s + (r.usd ?? 0), 0);
  const krw = cashRows.filter((r) => r.cash?.currency === 'KRW').reduce((s, r) => s + r.krw, 0);

  return (
    <div className={styles.modalBody}>
      <p className={clsx('t-label', styles.muted)}>{t.turnOff.cancelOrders}</p>
      {plan.isPending ? (
        <Skeleton text="body" width={220} />
      ) : orders.length > 0 ? (
        <ul className={styles.modalOrders}>
          {orders.map((o) => (
            <li key={o.id} className={styles.modalOrder}>
              <p className={styles.modalOrderHead}>
                <Hourglass size={16} aria-hidden />
                <span className="t-label">{cancelHead(o, now)}</span>
              </p>
              <p className="t-body">{cancelBody(o)}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className={clsx('t-body', styles.muted)}>{t.turnOff.noOrders}</p>
      )}
      {home.isPending && currencies.size > 0 ? <Skeleton text="caption" width={200} /> : null}
      {home.data && currencies.has('USD') && usd > 0 ? (
        <p className={clsx('t-caption', styles.muted)}>{cashStaysLine('USD', usd)}</p>
      ) : null}
      {home.data && currencies.has('KRW') && krw > 0 ? (
        <p className={clsx('t-caption', styles.muted)}>{cashStaysLine('KRW', krw)}</p>
      ) : null}
      <div className={styles.chips}>
        <InfoChip>{t.turnOff.holdingsStay}</InfoChip>
        <InfoChip>{t.turnOff.paperContinues}</InfoChip>
      </div>
      {failed ? (
        <p className={clsx('t-caption', styles.error)} role="alert">
          {t.turnOff.failed}
        </p>
      ) : null}
    </div>
  );
}

export function TurnOffSection({
  now,
  ref,
}: {
  now: string | null;
  ref?: Ref<HTMLDivElement> | undefined;
}) {
  const [open, setOpen] = useState(false);
  const turnOff = useTurnLiveOff();
  const busy = turnOff.isPending;

  return (
    <div ref={ref} className={styles.turnOff}>
      <Button
        kind="danger"
        className={styles.wide}
        onClick={() => {
          turnOff.reset();
          setOpen(true);
        }}
      >
        {t.turnOff.button}
      </Button>
      <p className={clsx('t-caption', styles.muted)}>{t.turnOff.note}</p>
      <ConfirmModal
        open={open}
        title={t.turnOff.title}
        cancelLabel={t.turnOff.cancel}
        confirmLabel={busy ? t.turnOff.busy : t.turnOff.confirm}
        onCancel={() => {
          if (!busy) setOpen(false);
        }}
        onConfirm={() => {
          if (busy) return;
          turnOff.mutate(undefined, {
            onSuccess: () => {
              setOpen(false);
            },
          });
        }}
      >
        <OffDetails now={now} failed={turnOff.isError} />
      </ConfirmModal>
    </div>
  );
}
