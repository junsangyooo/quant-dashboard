// 실전 끄기 (Figma 1:64317 · 1:64669): a red wide button and a line; it opens a centred modal with
// the orders that will be cancelled, the cash that stays, two chips and [취소][끄기]. No PIN —
// a valid session is enough (인계 7), also while PIN entry is locked.
import clsx from 'clsx';
import { useState, type Ref } from 'react';
import { Hourglass } from 'lucide-react';
import { modeCopy as t } from '../../copy/mode';
import { useTurnLiveOff } from '../../api/queries';
import type { Currency, ModeResponse } from '../../api/types';
import { Button } from '../../components/Buttons';
import { InfoChip } from '../../components/Chips';
import { ConfirmModal } from '../../components/ConfirmModal';
import { cancelBody, cancelHead, cashStaysLine } from './text';
import styles from './Mode.module.css';

type OffPreview = ModeResponse['offPreview'];

/**
 * What turning live off does (CONTRACT ModeResponse.offPreview): the pending orders it cancels
 * and, for the currency of each cancelled buy, the cash that stays ('달러 현금 $125.67은 계좌에
 * 남아요' — the design shows that one line, not every cash balance the server lists).
 */
function OffDetails({
  now,
  failed,
  offPreview,
}: {
  now: string | null;
  failed: boolean;
  offPreview: OffPreview;
}) {
  const orders = offPreview?.cancel ?? [];
  const currencies = new Set<Currency>(
    orders.filter((o) => o.side === 'buy').map((o) => o.instrument?.currency ?? 'KRW'),
  );
  const cash = (offPreview?.cash ?? []).filter((c) => currencies.has(c.currency));

  return (
    <div className={styles.modalBody}>
      <p className={clsx('t-label', styles.muted)}>{t.turnOff.cancelOrders}</p>
      {orders.length > 0 ? (
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
      {cash.map((c) => (
        <p key={c.currency} className={clsx('t-caption', styles.muted)}>
          {c.currency === 'USD' ? cashStaysLine('USD', c.usd) : cashStaysLine('KRW', c.krw)}
        </p>
      ))}
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
  offPreview,
  ref,
}: {
  now: string | null;
  offPreview: OffPreview;
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
        <OffDetails now={now} failed={turnOff.isError} offPreview={offPreview} />
      </ConfirmModal>
    </div>
  );
}
