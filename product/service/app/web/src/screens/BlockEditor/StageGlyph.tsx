// 단계 머리 아이콘(그림 V2-23의 단계 목록 · 블록 머리).
import {
  ChartColumn,
  Clock3,
  Filter,
  ListFilter,
  MinusCircle,
  PlusCircle,
  TrendingUp,
} from 'lucide-react';
import type { StageId } from '../../api/v2';

const ICONS = {
  universe: ChartColumn,
  signal: TrendingUp,
  filter: Filter,
  select: ListFilter,
  buy: PlusCircle,
  sell: MinusCircle,
  weight: Clock3,
} as const;

export function StageGlyph({ stage, size = 16 }: { stage: StageId; size?: number }) {
  const Icon = ICONS[stage];
  return <Icon size={size} aria-hidden />;
}
