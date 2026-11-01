// Stage icons and accent colors of the seven stages (Figma MVP 전략 편집 · 요약).
import clsx from 'clsx';
import {
  ChartColumnBig,
  ChartLine,
  ChartPie,
  CircleMinus,
  CirclePlus,
  ListFilter,
  Split,
  type LucideIcon,
} from 'lucide-react';
import type { SlotKey } from '../api/mvp';
import styles from './StageIcon.module.css';

const ICON: Record<SlotKey, LucideIcon> = {
  universe: ChartColumnBig,
  signal: ChartLine,
  filter: Split,
  select: ListFilter,
  buy: CirclePlus,
  sell: CircleMinus,
  weight: ChartPie,
};

/** data(①②) · condition(③④) · action(⑤⑥) · weight(⑦) — the site's node colors. */
export const STAGE_TONE: Record<SlotKey, 'data' | 'condition' | 'action' | 'weight'> = {
  universe: 'data',
  signal: 'data',
  filter: 'condition',
  select: 'condition',
  buy: 'action',
  sell: 'action',
  weight: 'weight',
};

export function StageIcon({ slot, size = 16 }: { slot: SlotKey; size?: number }) {
  const Icon = ICON[slot];
  return <Icon size={size} className={clsx(styles.icon, styles[STAGE_TONE[slot]])} aria-hidden />;
}
