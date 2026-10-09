// 요약 타일 3개: 리밸런싱 [n]회 (mini cells) · 수수료 [n]원 (mini bars) · 확인 [n]회 (ok/fail bar)
// (Figma 1:59344 '올해 타일', 1:58215).
import clsx from 'clsx';
import { ArrowLeftRight, Play, Receipt, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import type { HistoryResponse } from '../../api/types';
import { CalendarCell } from '../../components/Markers';
import { historyCopy as hc } from '../../copy/history';
import { formatKrw } from '../../lib/format';
import { rebalanceCells } from './historyModel';
import styles from './History.module.css';

function Tile({
  icon: Icon,
  label,
  value,
  picture,
  note,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  picture: ReactNode;
  note: string;
}) {
  return (
    <div className={styles.tile}>
      <p className={styles.tileHead}>
        <Icon size={14} aria-hidden />
        <span className="t-label">{label}</span>
      </p>
      <p className="t-title">{value}</p>
      <div className={styles.tilePicture} aria-hidden>
        {picture}
      </div>
      <p className={clsx('t-caption', styles.muted)}>{note}</p>
    </div>
  );
}

const FEE_BAR = { width: 10, gap: 4, height: 16 } as const;

/** One bar per rebalance, tallest = 16px (Figma '타일 수수료' 그림). */
function FeeBars({ fees }: { fees: readonly number[] }) {
  const max = Math.max(...fees, 0);
  const shown = fees.slice(-7);
  return (
    <svg
      width={shown.length * (FEE_BAR.width + FEE_BAR.gap)}
      height={FEE_BAR.height}
      className={styles.svg}
    >
      {shown.map((fee, i) => {
        const h = max > 0 ? Math.max(1, Math.round((fee / max) * FEE_BAR.height * 100) / 100) : 0;
        return (
          <rect
            key={i}
            className={styles.feeBar}
            x={i * (FEE_BAR.width + FEE_BAR.gap)}
            y={FEE_BAR.height - h}
            width={FEE_BAR.width}
            height={h}
            rx={2}
          />
        );
      })}
    </svg>
  );
}

/** Checks as one bar; failed checks are red at the end (at least 4px, Figma '타일 실행'). */
function CheckBar({ count, failed }: { count: number; failed: number }) {
  if (count === 0) return <span className={clsx(styles.checkBar, styles.checkBarEmpty)} />;
  const failPct = (failed / count) * 100;
  return (
    <span className={styles.checkBar}>
      {failed > 0 ? (
        <span className={styles.checkFail} style={{ width: `max(4px, ${String(failPct)}%)` }} />
      ) : null}
    </span>
  );
}

export interface SummaryTilesProps {
  tiles: HistoryResponse['tiles'];
  fees: readonly number[];
}

export function SummaryTiles({ tiles, fees }: SummaryTilesProps) {
  return (
    <div className={styles.tiles}>
      <Tile
        icon={ArrowLeftRight}
        label={hc.tiles.rebalance}
        value={hc.tiles.times(tiles.rebalances.count)}
        picture={
          <span className={styles.miniCells}>
            {rebalanceCells(tiles.rebalances).map((cell, i) => (
              <CalendarCell key={i} state={cell} />
            ))}
          </span>
        }
        note={hc.tiles.partialFailed(tiles.rebalances.partialFailed)}
      />
      <Tile
        icon={Receipt}
        label={hc.tiles.fees}
        value={formatKrw(tiles.fees.krw)}
        picture={<FeeBars fees={fees} />}
        note={hc.tiles.taxExcluded}
      />
      <Tile
        icon={Play}
        label={hc.tiles.checks}
        value={hc.tiles.times(tiles.checks.count)}
        picture={<CheckBar count={tiles.checks.count} failed={tiles.checks.failed} />}
        note={hc.tiles.failed(tiles.checks.failed)}
      />
    </div>
  );
}
