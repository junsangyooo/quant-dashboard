// 원화 · 달러 (D47·D48, 2026-10-13): the live ledger runs on the money as deposited, so the mix of
// won and dollars is the owner's. The card says how much to convert for the targets (when the mix
// is off by more than the band) and the money of today that waits for the next trading day. It is
// information beside the to-dos, never one of them. Used by the mode and health screens; the plan
// screen shows the same lines in the rule card and its 예정 list.
import clsx from 'clsx';
import { useId } from 'react';
import { ArrowLeftRight } from 'lucide-react';
import { fxMixText, fxSuggestionText, newMoneyText } from '../api/adapters';
import type { FxSuggestion, LiveCash } from '../api/types';
import { copy } from '../copy';
import styles from './LiveMoney.module.css';

/** Whether the live ledger's money has anything to say (a suggestion or money of today). */
export function hasLiveMoney(cash: LiveCash | null | undefined): cash is LiveCash {
  return cash != null && (cash.newMoney !== null || cash.fxSuggestion !== null);
}

/** '약 5,000,000원을 달러로 바꾸면 50:50' + '지금 한국 100 : 미국 0 · 토스 앱에서 바꾸면 …'. */
export function FxSuggestionLines({
  suggestion,
  className,
}: {
  suggestion: FxSuggestion;
  className?: string | undefined;
}) {
  return (
    <div className={clsx(styles.lines, className)}>
      <p className="t-label">{fxSuggestionText(suggestion)}</p>
      <p className={clsx('t-caption', styles.muted)}>
        {`${fxMixText(suggestion)} · ${copy.liveMoney.suggestionNote}`}
      </p>
    </div>
  );
}

export function LiveMoneyCard({
  cash,
  className,
}: {
  cash: LiveCash;
  className?: string | undefined;
}) {
  const titleId = useId();
  return (
    <section className={clsx(styles.card, className)} aria-labelledby={titleId}>
      <div className={styles.head}>
        <ArrowLeftRight size={20} className={styles.icon} aria-hidden />
        <h2 id={titleId} className="t-body-strong">
          {copy.liveMoney.title}
        </h2>
      </div>
      {cash.fxSuggestion ? <FxSuggestionLines suggestion={cash.fxSuggestion} /> : null}
      {cash.newMoney ? <p className="t-body">{newMoneyText(cash.newMoney)}</p> : null}
    </section>
  );
}
