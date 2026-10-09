// 지금 자산 (Figma '지금 자산'): '[장부] 자산 · [시작일]부터' + 예시 + 낡음 | 기준 chip → 총액 →
// 손익 chip · 손대지 않았을 때 chip → 계획 칩 줄 (상태 칩 + 다음 행동 ›, → 계획).
import clsx from 'clsx';
import { useState } from 'react';
import { Link } from 'react-router';
import { ChevronRight } from 'lucide-react';
import { ruleStatusChip } from '../../api/adapters';
import { useConnection } from '../../api/queries';
import type { HomeResponse } from '../../api/types';
import { InfoChip, RebalanceChip } from '../../components/Chips';
import { ExampleChip, OfflineChip, StaleMark } from '../../components/State';
import { copy } from '../../copy';
import { homeCopy } from '../../copy/home';
import {
  formatFxRate,
  formatKrw,
  formatKrwSigned,
  formatMonthDay,
  formatPercentSigned,
  formatTime,
  pnlDirection,
} from '../../lib/format';
import { nextActionText } from '../Plan/words';
import { Sheet } from './Sheet';
import styles from './Home.module.css';

/** '모의투자 자산 · 7/1부터', '실전 자산 · 9/1 시작', '모의투자 시작 금액'. */
export function heroLabel(home: HomeResponse): string {
  const h = homeCopy.hero;
  const ledger = copy.mode[home.ledger];
  const start = formatMonthDay(home.startDate);
  if (home.trend.empty === 'before-first-check') return h.startAmount(ledger);
  if (home.trend.empty === 'before-first-fill') return `${h.assets(ledger)} · ${h.started(start)}`;
  return `${h.assets(ledger)} · ${h.since(start)}`;
}

/** '▲ +243,800원 · +2.44%' (pct hidden when its base is 0 or less). */
export function pnlText(pnl: NonNullable<HomeResponse['pnl']>): string {
  const dir = pnlDirection(pnl.amount);
  const arrow = dir === 'gain' ? homeCopy.hero.up : dir === 'loss' ? homeCopy.hero.down : '';
  const body = homeCopy.hero.pnl(
    formatKrwSigned(pnl.amount),
    pnl.pct === null ? null : formatPercentSigned(pnl.pct, 2),
  );
  return arrow ? `${arrow} ${body}` : body;
}

function BasisSheet({ home, onClose }: { home: HomeResponse; onClose: () => void }) {
  const b = home.basis;
  const s = homeCopy.basisSheet;
  const lines = [
    b.krClose !== null ? s.kr(formatMonthDay(b.krClose)) : null,
    b.usClose !== null ? s.us(formatMonthDay(b.usClose)) : null,
    b.fxRate !== null && b.fxAt !== null ? s.fx(formatFxRate(b.fxRate), formatTime(b.fxAt)) : null,
    b.coinAt ? s.coin(formatTime(b.coinAt)) : null,
  ].filter((l): l is string => l !== null);
  return (
    <Sheet title={homeCopy.hero.basis(formatTime(b.valuedAt))} onClose={onClose}>
      <ul className={styles.sheetLines}>
        {lines.map((l) => (
          <li key={l} className="t-body">
            {l}
          </li>
        ))}
      </ul>
    </Sheet>
  );
}

function BaselineSheet({ onClose }: { onClose: () => void }) {
  return (
    <Sheet title={homeCopy.baselineSheet.title} onClose={onClose}>
      <ul className={styles.sheetLines}>
        {homeCopy.baselineSheet.lines.map((l) => (
          <li key={l} className="t-body">
            {l}
          </li>
        ))}
      </ul>
    </Sheet>
  );
}

/** 계획 칩 줄: status chip + next action ›; before the first check only the words (명세 정정). */
export function PlanChipLine({ home, now }: { home: HomeResponse; now: string | null }) {
  const { status, next } = home.planChip;
  const rule = home.planCard?.rule;
  const chip = ruleStatusChip(status, rule?.ai ?? false);
  const text = nextActionText(next, { now });
  return (
    <Link to="/plan" className={styles.planLine}>
      {next.kind !== 'first-check' ? (
        <RebalanceChip state={chip.state}>{chip.label}</RebalanceChip>
      ) : null}
      <span className="t-label">{text}</span>
      <ChevronRight size={16} className={styles.muted} aria-hidden />
    </Link>
  );
}

export function Hero({ home, now }: { home: HomeResponse; now: string | null }) {
  const [sheet, setSheet] = useState<'basis' | 'baseline' | null>(null);
  const connection = useConnection();
  const close = () => {
    setSheet(null);
  };
  const beforeCheck = home.trend.empty === 'before-first-check';
  const pnl = home.pnl;
  const dir = pnl ? pnlDirection(pnl.amount) : 'flat';

  return (
    <section className={styles.hero} aria-label={heroLabel(home)}>
      <div className={styles.labelRow}>
        <div className={styles.label}>
          <span className={clsx('t-caption', styles.muted)}>{heroLabel(home)}</span>
          <ExampleChip show={home.example} />
          <StaleMark stale={home.stale} section="hero" />
        </div>
        {connection === 'offline' ? (
          <OfflineChip />
        ) : !beforeCheck ? (
          <InfoChip
            onClick={() => {
              setSheet('basis');
            }}
          >
            {homeCopy.hero.basis(formatTime(home.basis.valuedAt))}
          </InfoChip>
        ) : null}
      </div>
      <p className="t-display">{formatKrw(home.total)}</p>
      <div className={styles.chips}>
        <InfoChip>
          <span className={clsx(pnl ? styles[dir] : styles.primary)}>
            {pnl
              ? pnlText(pnl)
              : beforeCheck
                ? homeCopy.hero.pnlAfterFirstCheck
                : homeCopy.hero.pnlAfterFirstFill}
          </span>
        </InfoChip>
        {home.baseline ? (
          <InfoChip
            onClick={() => {
              setSheet('baseline');
            }}
          >
            {homeCopy.hero.baseline(formatPercentSigned(home.baseline.pct, 2))}
          </InfoChip>
        ) : null}
      </div>
      <PlanChipLine home={home} now={now} />
      {sheet === 'basis' ? <BasisSheet home={home} onClose={close} /> : null}
      {sheet === 'baseline' ? <BaselineSheet onClose={close} /> : null}
    </section>
  );
}
