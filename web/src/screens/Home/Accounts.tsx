// 계좌별 보기 (the owner, 2026-10-12; no Figma frame yet): in 전체 the two account tiles under the
// total (each in its own money) and the 환율 효과 sheet that adds the parts up to the won P&L;
// in 한국 ₩ · 미국 $ the hero of one account. CONTRACT.md HomeResponse.accounts.
import clsx from 'clsx';
import { useState } from 'react';
import { Link } from 'react-router';
import { ChevronRight } from 'lucide-react';
import type { AccountId, HomeAccount, HomeAccounts, HomeResponse } from '../../api/types';
import { ChartTable } from '../../charts/ChartTable';
import { Waterfall } from '../../charts/Waterfall';
import type { WaterfallStep } from '../../charts/geometry/waterfall';
import { Flag } from '../../components/Badges';
import { InfoChip } from '../../components/Chips';
import { StaleTag } from '../../components/Notices';
import { ExampleChip, OfflineChip, StaleMark } from '../../components/State';
import { useConnection } from '../../api/queries';
import { homeCopy } from '../../copy/home';
import {
  formatFxRate,
  formatKrwSigned,
  formatMonthDay,
  formatPercentSigned,
  formatTime,
  formatUsdSigned,
  pnlDirection,
} from '../../lib/format';
import { formatMoney, moneyDirection, pnlText } from './money';
import { Sheet } from './Sheet';
import styles from './Home.module.css';

const a = homeCopy.accounts;

/** '?account=kr' — the account views live in the address (back returns to 전체). */
export function accountHref(id: AccountId): string {
  return `?account=${id}`;
}

/** History state of an account view opened from 전체: 전체 then steps back instead of pushing. */
export const FROM_ALL = { fromAll: true } as const;

export function isFromAll(state: unknown): boolean {
  return (
    typeof state === 'object' && state !== null && 'fromAll' in state && state.fromAll === true
  );
}

/** '▲ +484,683원 · +9.41%', '▼ −$149.95 · −4.30%'; the tile of an empty account says so. */
export function accountPnlText(account: HomeAccount): string {
  return account.pnl ? pnlText(account.pnl, account.currency) : a.emptyShort;
}

/**
 * '[국기] 한국 계좌  +9.41%' / '5,368,683원' / '▲ +484,683원'. The % sits on the name line so the
 * amount line never wraps at 390 (two tiles share 350px; '▲ +668,698원 · +14.55%' is 151px of 147).
 */
function AccountTile({ account }: { account: HomeAccount }) {
  const pnl = account.pnl;
  const dir = pnl ? moneyDirection(pnl.amount, account.currency) : 'flat';
  return (
    <Link to={accountHref(account.id)} state={FROM_ALL} className={styles.tile}>
      <span className={styles.tileHead}>
        <Flag country={account.id} decorative />
        <span className="t-label">{a.name[account.id]}</span>
        {account.stale ? <StaleTag /> : null}
        {pnl && pnl.pct !== null ? (
          <span className={clsx('t-caption', styles.tilePct, styles[dir])}>
            {formatPercentSigned(pnl.pct, 2)}
          </span>
        ) : null}
      </span>
      <span className="t-figure">{formatMoney(account.total, account.currency)}</span>
      <span className={clsx('t-caption', pnl ? styles[dir] : styles.muted)}>
        {pnl ? pnlText({ amount: pnl.amount, pct: null }, account.currency) : a.emptyShort}
      </span>
    </Link>
  );
}

/** Under the total in 전체: 한국 계좌 · 미국 계좌, each in its own money; a tile opens its view. */
export function AccountTiles({ accounts }: { accounts: HomeAccounts }) {
  return (
    <ul className={styles.tiles}>
      {accounts.list.map((account) => (
        <li key={account.id}>
          <AccountTile account={account} />
        </li>
      ))}
    </ul>
  );
}

/** The won P&L in its three parts, from zero: 한국 → 미국 (in won) → 환율 효과 = 전체 손익. */
export function splitSteps(home: HomeResponse, accounts: HomeAccounts): WaterfallStep[] {
  const { kr, us, fx } = accounts.split;
  return [
    { key: 'kr', label: a.name.kr, kind: 'change', value: kr },
    { key: 'us', label: a.name.us, kind: 'change', value: us },
    { key: 'fx', label: a.fxEffect, kind: 'change', value: fx },
    { key: 'total', label: a.split.total, kind: 'anchor', value: home.pnl?.amount ?? kr + us + fx },
  ];
}

export function SplitSheet({
  home,
  accounts,
  onClose,
}: {
  home: HomeResponse;
  accounts: HomeAccounts;
  onClose: () => void;
}) {
  const steps = splitSteps(home, accounts);
  const value = (s: WaterfallStep) => formatKrwSigned(s.value);
  const us = accounts.list.find((x) => x.id === 'us');
  const rate = home.basis.fxRate;
  return (
    <Sheet title={a.split.title} onClose={onClose}>
      <Waterfall
        steps={steps}
        formatValue={value}
        label={steps.map((s) => `${s.label} ${value(s)}`).join(' · ')}
      />
      <div className="sr-only">
        <ChartTable
          caption={a.split.title}
          columns={[a.split.title, a.split.total]}
          rows={steps.map((s) => [s.label, value(s)])}
        />
      </div>
      <ul className={styles.sheetLines}>
        {us?.pnl && rate !== null ? (
          <li className={clsx('t-caption', styles.muted)}>
            {`${a.name.us} ${a.split.converted(formatUsdSigned(us.pnl.amount), formatFxRate(rate))}`}
          </li>
        ) : null}
        <li className={clsx('t-caption', styles.muted)}>{`${a.fxEffect} · ${a.split.fxNote}`}</li>
      </ul>
    </Sheet>
  );
}

/** '환율 효과 −33,592원 ›' under the P&L in 전체; opens the sheet that adds the parts up. */
export function FxEffectLine({ home, accounts }: { home: HomeResponse; accounts: HomeAccounts }) {
  const [open, setOpen] = useState(false);
  const fx = accounts.split.fx;
  const dir = pnlDirection(fx);
  return (
    <>
      <button
        type="button"
        className={styles.fxLine}
        onClick={() => {
          setOpen(true);
        }}
      >
        <span className={clsx('t-caption', styles.muted)}>{a.fxEffect}</span>
        <span className={clsx('t-label', styles[dir])}>{formatKrwSigned(fx)}</span>
        <ChevronRight size={14} className={styles.muted} aria-hidden />
      </button>
      {open ? (
        <SplitSheet
          home={home}
          accounts={accounts}
          onClose={() => {
            setOpen(false);
          }}
        />
      ) : null}
    </>
  );
}

function AccountBasisSheet({
  home,
  account,
  onClose,
}: {
  home: HomeResponse;
  account: HomeAccount;
  onClose: () => void;
}) {
  const b = home.basis;
  const s = homeCopy.basisSheet;
  // An account's money moves with its own market only: its close, no rate.
  const close = account.id === 'kr' ? b.krClose : b.usClose;
  const line =
    close === null
      ? null
      : account.id === 'kr'
        ? s.kr(formatMonthDay(close))
        : s.us(formatMonthDay(close));
  return (
    <Sheet title={homeCopy.hero.basis(formatTime(b.valuedAt))} onClose={onClose}>
      <ul className={styles.sheetLines}>
        {line !== null ? <li className="t-body">{line}</li> : null}
      </ul>
    </Sheet>
  );
}

/** 한국 ₩ · 미국 $: '[계좌] · 7/1부터' | 기준 → the account's value → its P&L, in its money. */
export function AccountHero({ home, account }: { home: HomeResponse; account: HomeAccount }) {
  const [sheet, setSheet] = useState(false);
  const connection = useConnection();
  const label = a.since(a.name[account.id], formatMonthDay(home.startDate));
  const stale: readonly 'hero'[] = account.stale ? ['hero'] : [];
  const dir = account.pnl ? moneyDirection(account.pnl.amount, account.currency) : 'flat';
  return (
    <section className={styles.hero} aria-label={label}>
      <div className={styles.labelRow}>
        <div className={styles.label}>
          <Flag country={account.id} decorative />
          <span className={clsx('t-caption', styles.muted)}>{label}</span>
          <ExampleChip show={home.example} />
          <StaleMark stale={stale} section="hero" />
        </div>
        {connection === 'offline' ? (
          <OfflineChip />
        ) : (
          <InfoChip
            onClick={() => {
              setSheet(true);
            }}
          >
            {homeCopy.hero.basis(formatTime(home.basis.valuedAt))}
          </InfoChip>
        )}
      </div>
      <p className="t-display">{formatMoney(account.total, account.currency)}</p>
      {account.pnl ? (
        <div className={styles.chips}>
          <InfoChip>
            <span className={styles[dir]}>{accountPnlText(account)}</span>
          </InfoChip>
        </div>
      ) : null}
      {sheet ? (
        <AccountBasisSheet
          home={home}
          account={account}
          onClose={() => {
            setSheet(false);
          }}
        />
      ) : null}
    </section>
  );
}

/**
 * An account no money reached yet: '미국 계좌는 비어 있어요' in place of its graph and rows; dollars
 * only come by conversion, so 미국 계좌 adds when it fills.
 */
export function AccountEmpty({ account }: { account: HomeAccount }) {
  return (
    <section className={styles.emptyAccount} aria-label={a.name[account.id]}>
      <p className="t-body">{a.empty(a.name[account.id])}</p>
      {account.id === 'us' ? <p className={clsx('t-caption', styles.muted)}>{a.fillsBy}</p> : null}
    </section>
  );
}
