// 조건 배치와 선 모양: 자동 정렬(한 줄 열) · 처음 열 때 배치(진입 줄 · 매수 줄 두 줄) · 좁은 화면 위→아래.
// 열은 단계 순서(① · ② · ③ · ④ · ⑤ · ⑥, ② 뒤에 ③을 이으면 ③은 다음 열), 열 안은 경로 순서, ⑦은 ⑤ 아래.
import type { Graph, GraphNode, SlotKey } from '../api/mvp';
import { entryPaths, outgoing, type RuleCatalog, sellPaths, stageOf } from './rules';

export interface Size {
  w: number;
  h: number;
}
export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}
export type Sizes = Record<string, Size>;

/** 편집 캔버스의 조건 카드 폭과 열 간격(다른 화면과 같은 카드 폭 · 글자 중간 줄바꿈 0). */
export const CARD_W = 150;
export const COL_PITCH = 216;
export const ROW_GAP = 34;
const ENTRY: ReadonlySet<SlotKey> = new Set(['universe', 'signal', 'filter', 'select']);
const STAGE_COL: Record<SlotKey, number> = {
  universe: 0,
  signal: 1,
  filter: 2,
  select: 3,
  buy: 4,
  sell: 5,
  weight: 4,
};

interface Plan {
  col: Record<string, number>;
  lane: Record<string, number>;
  shared: Set<string>;
  buyCol: number;
  lanes: number;
  sellLanes: number;
  isSell: Set<string>;
}

/** 열 번호(단계 순서 + 이어진 깊이) · 경로 순서(lane). */
function plan(cat: RuleCatalog, g: Graph): Plan {
  const by = new Map(g.nodes.map((n) => [n.id, n]));
  const stage = (id: string) => stageOf(cat, by.get(id)?.piece ?? '');
  const out = outgoing(g);
  const entry = entryPaths(cat, g);
  const sells = sellPaths(cat, g);
  const col: Record<string, number> = {};
  // 진입 쪽: 유니버스에서 가장 긴 거리(② · ③ 사슬이 길면 열이 늘어난다)
  for (const p of entry) {
    p.nodes.forEach((id, i) => {
      if (ENTRY.has(stage(id))) col[id] = Math.max(col[id] ?? 0, i);
    });
  }
  const entryMax = Math.max(0, ...Object.values(col));
  // ④는 진입 쪽 마지막 열
  for (const n of g.nodes)
    if (stage(n.id) === 'select' && col[n.id] !== undefined) col[n.id] = entryMax;
  const anySelect = g.nodes.some((n) => stage(n.id) === 'select');
  const reached = Object.keys(col).length > 0;
  const buyCol = reached ? entryMax + 1 : anySelect ? 4 : 3;
  for (const n of g.nodes) if (stage(n.id) === 'buy') col[n.id] = buyCol;
  for (const p of sells)
    p.nodes.forEach((id, i) => {
      if (i > 0) col[id] = Math.max(col[id] ?? 0, buyCol + i);
    });
  for (const n of g.nodes) if (stage(n.id) === 'weight') col[n.id] = buyCol;
  // 경로에 없는 조건: 단계 기본 열(앞뒤로 이어진 것이 있으면 그 뒤)
  for (const n of g.nodes) {
    if (col[n.id] !== undefined) continue;
    const s = stage(n.id);
    col[n.id] =
      s === 'sell'
        ? buyCol + 1
        : s === 'buy' || s === 'weight'
          ? buyCol
          : Math.min(STAGE_COL[s], buyCol - 1);
  }
  for (let k = 0; k < 3; k++) {
    for (const n of g.nodes) {
      for (const d of out.get(n.id) ?? []) {
        if (stage(d) === 'weight' || stage(n.id) === 'weight') continue;
        if ((col[d] ?? 0) <= (col[n.id] ?? 0) && stage(d) !== 'buy') col[d] = (col[n.id] ?? 0) + 1;
      }
    }
  }
  // lane: 처음 지나는 경로 번호. 모든 경로가 지나면 가운데(shared)
  const lane: Record<string, number> = {};
  const count: Record<string, number> = {};
  entry.forEach((p, i) => {
    for (const id of p.nodes) {
      lane[id] ??= i;
      count[id] = (count[id] ?? 0) + 1;
    }
  });
  const sellCount: Record<string, number> = {};
  sells.forEach((p, i) => {
    for (const id of p.nodes.slice(1)) {
      lane[id] ??= i;
      sellCount[id] = (sellCount[id] ?? 0) + 1;
    }
  });
  const shared = new Set<string>();
  for (const [id, c] of Object.entries(count))
    if (entry.length > 1 && c === entry.length) shared.add(id);
  if (entry.length <= 1) for (const id of Object.keys(count)) shared.add(id);
  for (const [id, c] of Object.entries(sellCount)) if (c === sells.length) shared.add(id);
  const isSell = new Set(Object.keys(sellCount));
  return {
    col,
    lane,
    shared,
    buyCol,
    lanes: Math.max(1, entry.length),
    sellLanes: Math.max(1, sells.length),
    isSell,
  };
}

function sz(sizes: Sizes, id: string, fallback: Size): Size {
  return sizes[id] ?? fallback;
}

function order(p: Plan, ids: string[], g: Graph): string[] {
  const idx = new Map(g.nodes.map((n, i) => [n.id, i]));
  return [...ids].sort(
    (a, b) => (p.lane[a] ?? 99) - (p.lane[b] ?? 99) || (idx.get(a) ?? 0) - (idx.get(b) ?? 0),
  );
}

/** 열마다 경로 줄(lane)에 맞춰 놓는다: 모든 경로가 지나는 조건은 가운데 줄, 나머지는 경로 번호 줄. 겹치면 아래로. */
function stackColumns(
  g: Graph,
  p: Plan,
  ids: string[],
  sizes: Sizes,
  colX: (c: number) => number,
  centerY: number,
  card: Size,
): Record<string, { x: number; y: number }> {
  const cols = new Map<number, string[]>();
  for (const id of ids) {
    const c = p.col[id] ?? 0;
    cols.set(c, [...(cols.get(c) ?? []), id]);
  }
  const maxH = Math.max(card.h, ...ids.map((id) => sz(sizes, id, card).h));
  const pitch = maxH + ROW_GAP * 1.3;
  const pos: Record<string, { x: number; y: number }> = {};
  for (const [c, list] of cols) {
    const placed = order(p, list, g).map((id) => {
      const lanes = p.isSell.has(id) ? p.sellLanes : p.lanes;
      const lane =
        p.shared.has(id) || p.lane[id] === undefined ? (lanes - 1) / 2 : (p.lane[id] ?? 0);
      const h = sz(sizes, id, card).h;
      return { id, h, y: centerY + (lane - (lanes - 1) / 2) * pitch - h / 2 };
    });
    // 경로에 없는 조건(lane 없음)이 겹치면 아래로
    placed.sort((a, b) => a.y - b.y);
    for (let i = 1; i < placed.length; i++) {
      const prev = placed[i - 1];
      const cur = placed[i];
      if (prev && cur && cur.y < prev.y + prev.h + 14) cur.y = prev.y + prev.h + 14;
    }
    for (const q of placed) pos[q.id] = { x: colX(c), y: Math.round(q.y) };
  }
  return pos;
}

/** 자동 정렬: 한 줄로 열을 맞추고 ⑦ 비중은 ⑤ 매수 아래. */
export function autoLayout(
  cat: RuleCatalog,
  g: Graph,
  sizes: Sizes,
  card: Size = { w: CARD_W, h: 64 },
  pitch = COL_PITCH,
  origin = { x: 40, y: 260 },
): Record<string, { x: number; y: number }> {
  const p = plan(cat, g);
  const stage = (n: GraphNode) => stageOf(cat, n.piece);
  const main = g.nodes.filter((n) => stage(n) !== 'weight').map((n) => n.id);
  const pos = stackColumns(g, p, main, sizes, (c) => origin.x + c * pitch, origin.y, card);
  const buy = g.nodes.find((n) => stage(n) === 'buy');
  const buyPos = buy ? pos[buy.id] : undefined;
  const bx = buyPos?.x ?? origin.x + p.buyCol * pitch;
  let y = (buyPos?.y ?? origin.y) + (buy ? sz(sizes, buy.id, card).h : 0) + ROW_GAP * 2.5;
  // ⑤ 열의 다른 조건(매수가 아닌 것) 아래로
  for (const id of main) {
    if ((p.col[id] ?? -1) === p.buyCol && id !== buy?.id) {
      const q = pos[id];
      if (q) y = Math.max(y, q.y + sz(sizes, id, card).h + ROW_GAP * 2.5);
    }
  }
  g.nodes
    .filter((n) => stage(n) === 'weight')
    .forEach((n, i) => {
      pos[n.id] = { x: bx - i * pitch, y: Math.round(y) };
    });
  return pos;
}

/** 왼쪽 위 모서리가 (0, 0)이 되게 옮긴다. */
export function normalize(
  pos: Record<string, { x: number; y: number }>,
  keepX = false,
): Record<string, { x: number; y: number }> {
  const vals = Object.values(pos);
  if (vals.length === 0) return pos;
  const mx = keepX ? 0 : Math.min(...vals.map((p) => p.x));
  const my = Math.min(...vals.map((p) => p.y));
  return Object.fromEntries(Object.entries(pos).map(([k, p]) => [k, { x: p.x - mx, y: p.y - my }]));
}

/** 처음 열 때 · 두 줄 배치: 진입 줄(① ~ ④) 아래에 매수 줄(⑤ · ⑥), ⑦은 첫 열(또는 ⑤ 아래). */
export function wrapLayout(
  cat: RuleCatalog,
  g: Graph,
  sizes: Sizes,
  opts: {
    card?: Size;
    pitch?: number;
    origin?: { x: number; y: number };
    weightsUnderBuy?: boolean;
    bandGap?: number;
  } = {},
): Record<string, { x: number; y: number }> {
  const card = opts.card ?? { w: CARD_W, h: 64 };
  const pitch = opts.pitch ?? COL_PITCH;
  const origin = opts.origin ?? { x: 25, y: 196 };
  const p = plan(cat, g);
  const stage = (n: GraphNode) => stageOf(cat, n.piece);
  const top = g.nodes.filter((n) => ENTRY.has(stage(n))).map((n) => n.id);
  const pos = stackColumns(g, p, top, sizes, (c) => origin.x + c * pitch, origin.y, card);
  const bottomOfTop = Math.max(
    origin.y,
    ...top.map((id) => (pos[id]?.y ?? 0) + sz(sizes, id, card).h),
  );
  const band2 = bottomOfTop + (opts.bandGap ?? 116);
  const shift = p.buyCol - 1; // ⑤를 둘째 열로
  const rest = g.nodes.filter((n) => stage(n) === 'buy' || stage(n) === 'sell').map((n) => n.id);
  const restPos = stackColumns(g, p, rest, sizes, (c) => origin.x + (c - shift) * pitch, 0, card);
  // 매수 줄을 band2에서 시작: 가장 위 조건의 위쪽을 band2에 맞춘다
  const minY = Math.min(0, ...Object.values(restPos).map((q) => q.y));
  for (const [id, q] of Object.entries(restPos))
    pos[id] = { x: q.x, y: Math.round(q.y - minY + band2) };
  const buy = g.nodes.find((n) => stage(n) === 'buy');
  const buyPos = buy ? pos[buy.id] : undefined;
  const weights = g.nodes.filter((n) => stage(n) === 'weight');
  if (opts.weightsUnderBuy) {
    // 한 줄: 첫째는 ⑤ 바로 아래, 나머지는 그 왼쪽
    let y = (buyPos?.y ?? band2) + (buy ? sz(sizes, buy.id, card).h : 0) + ROW_GAP * 1.6;
    for (const id of rest) {
      const q = pos[id];
      if (q && q.x <= (buyPos?.x ?? 0) + 4 && q.y > (buyPos?.y ?? 0))
        y = Math.max(y, q.y + sz(sizes, id, card).h + ROW_GAP);
    }
    weights.forEach((n, i) => {
      pos[n.id] = { x: (buyPos?.x ?? origin.x + pitch) - i * pitch, y: Math.round(y) };
    });
  } else {
    const lowest = Math.max(band2, ...rest.map((id) => (pos[id]?.y ?? 0) + sz(sizes, id, card).h));
    let y = Math.max(
      (buyPos?.y ?? band2) + 90,
      lowest - weights.length * (card.h + ROW_GAP) + ROW_GAP,
    );
    for (const n of weights) {
      pos[n.id] = { x: origin.x, y: Math.round(y) };
      y += sz(sizes, n.id, card).h + ROW_GAP;
    }
  }
  return pos;
}

/** 넓은 읽기 전용 그래프: 열이 들어가면 한 줄, 넘치면 두 줄. */
export function readLayout(
  cat: RuleCatalog,
  g: Graph,
  sizes: Sizes,
  width: number,
  card: Size,
  pitch: number,
): Record<string, { x: number; y: number }> {
  const p = plan(cat, g);
  const cols = Math.max(0, ...Object.values(p.col)) + 1;
  if (cols * pitch - (pitch - card.w) <= width) {
    return autoLayout(cat, g, sizes, card, pitch, { x: 0, y: 0 });
  }
  return wrapLayout(cat, g, sizes, {
    card,
    pitch,
    origin: { x: 0, y: 0 },
    weightsUnderBuy: true,
    bandGap: 64,
  });
}

/** 좁은 화면(390 · 560 한 열): 위에서 아래로. 줄 = 단계 깊이, 줄 안은 경로 순서(모두 지나면 가운데). */
export function verticalLayout(
  cat: RuleCatalog,
  g: Graph,
  sizes: Sizes,
  width: number,
  card: Size,
  rowGap = 34,
): Record<string, { x: number; y: number }> {
  const p = plan(cat, g);
  const stage = (id: string) => stageOf(cat, g.nodes.find((n) => n.id === id)?.piece ?? '');
  const lanes = Math.min(4, p.lanes);
  const rows = new Map<number, string[]>();
  for (const n of g.nodes) {
    if (stage(n.id) === 'weight') continue;
    const c = p.col[n.id] ?? 0;
    rows.set(c, [...(rows.get(c) ?? []), n.id]);
  }
  const pos: Record<string, { x: number; y: number }> = {};
  const keys = [...rows.keys()].sort((a, b) => a - b);
  const weights = g.nodes.filter((n) => stage(n.id) === 'weight').map((n) => n.id);
  let y = 0;
  const half = width / 2;
  for (const r of keys) {
    const list = order(p, rows.get(r) ?? [], g);
    let rowH = Math.max(...list.map((id) => sz(sizes, id, card).h));
    const isBuyRow = list.some((id) => stage(id) === 'buy');
    if (isBuyRow && weights.length > 0) {
      // ⑦은 왼쪽에 쌓고 ⑤는 오른쪽
      let wy = y;
      for (const id of weights) {
        const s = sz(sizes, id, card);
        pos[id] = { x: Math.round(Math.max(0, half - 8 - s.w)), y: Math.round(wy) };
        wy += s.h + 10;
      }
      for (const id of list) pos[id] = { x: Math.round(half + 8), y: Math.round(y) };
      rowH = Math.max(rowH, wy - y - 10);
    } else if (
      list.length === 1 &&
      (p.shared.has(list[0] ?? '') ||
        lanes <= 1 ||
        (stage(list[0] ?? '') !== 'signal' && stage(list[0] ?? '') !== 'filter'))
    ) {
      const id = list[0] ?? '';
      const s = sz(sizes, id, card);
      const laneOf = p.lane[id];
      const center =
        p.shared.has(id) || lanes <= 1 || laneOf === undefined || stage(id) === 'sell'
          ? half
          : ((Math.min(laneOf, lanes - 1) + 0.5) * width) / lanes;
      pos[id] = {
        x: Math.round(Math.min(width - s.w, Math.max(0, center - s.w / 2))),
        y: Math.round(y),
      };
    } else {
      const entryRow = list.every((id) => stage(id) === 'signal' || stage(id) === 'filter');
      const slots = entryRow ? Math.max(lanes, list.length) : list.length;
      list.forEach((id, i) => {
        const s = sz(sizes, id, card);
        const laneOf = entryRow ? Math.min(p.lane[id] ?? i, slots - 1) : i;
        const center = ((laneOf + 0.5) * width) / slots;
        pos[id] = {
          x: Math.round(Math.min(width - s.w, Math.max(0, center - s.w / 2))),
          y: Math.round(y),
        };
      });
    }
    y += rowH + rowGap;
  }
  // 줄 안에서 겹치면 옆으로 민다
  return pos;
}

// ── 선 모양 ──────────────────────────────────────────────────────────────────

export interface EdgeGeom {
  d: string;
  /** 화살표 끝과 방향. */
  end: { x: number; y: number; dir: 'right' | 'down' | 'up' };
  mid: { x: number; y: number };
}

const R = 10;

/** 왼쪽 → 오른쪽 선: 오른쪽 연결점 → 왼쪽 연결점(곡선). 끝이 왼쪽에 있으면(두 줄 배치) 꺾은 선. */
/** 꺾은 선이 지날 가로줄: 조건 상자들을 세로로 겹친 띠로 묶고, 시작 조건이 든 띠와 다음 띠 사이 가운데. */
export function wrapMidY(boxes: readonly Box[], a: Box): number | null {
  const iv = boxes.map((b) => [b.y, b.y + b.h] as const).sort((x, y) => x[0] - y[0]);
  const bands: [number, number][] = [];
  for (const [t, bo] of iv) {
    const last = bands[bands.length - 1];
    if (last && t <= last[1] + 6) last[1] = Math.max(last[1], bo);
    else bands.push([t, bo]);
  }
  const i = bands.findIndex((b) => a.y + a.h >= b[0] && a.y + a.h <= b[1] + 0.5);
  const cur = bands[i];
  const next = bands[i + 1];
  if (!cur || !next) return null;
  return Math.round((cur[1] + next[0]) / 2);
}

export function edgeHorizontal(
  a: Box,
  b: Box,
  opts: { fromBelow?: boolean; elbow?: boolean; midY?: number | null } = {},
): EdgeGeom {
  if (opts.elbow) {
    // ⑦이 ⑤ 왼쪽 아래: 위로 나가 꺾어 ⑤ 아래로 들어간다
    const sx = Math.round(a.x + a.w / 2);
    const tx = Math.round(b.x + 36);
    const y2 = b.y + b.h;
    const midY = Math.round((a.y + y2) / 2);
    return {
      d: `M${String(sx)} ${String(a.y)} V${String(midY + R)} Q${String(sx)} ${String(midY)} ${String(sx + R)} ${String(midY)} H${String(tx - R)} Q${String(tx)} ${String(midY)} ${String(tx)} ${String(midY - R)} V${String(y2 + 2)}`,
      end: { x: tx, y: y2, dir: 'up' },
      mid: { x: (sx + tx) / 2, y: midY },
    };
  }
  if (opts.fromBelow) {
    const x = Math.round(b.x + b.w / 2);
    const y1 = a.y;
    const y2 = b.y + b.h;
    return {
      d: `M${String(x)} ${String(y1)} L${String(x)} ${String(y2 + 2)}`,
      end: { x, y: y2, dir: 'up' },
      mid: { x, y: (y1 + y2) / 2 },
    };
  }
  const sx = a.x + a.w;
  const sy = a.y + a.h / 2;
  const tx = b.x;
  const ty = b.y + b.h / 2;
  if (tx >= sx + 24 || tx >= a.x + 8) {
    const dx = Math.max(tx >= sx + 24 ? 36 : 70, (tx - sx) / 2);
    return {
      d: `M${String(sx)} ${String(sy)} C${String(sx + dx)} ${String(sy)} ${String(tx - dx)} ${String(ty)} ${String(tx - 2)} ${String(ty)}`,
      end: { x: tx, y: ty, dir: 'right' },
      mid: { x: (sx + tx) / 2, y: (sy + ty) / 2 },
    };
  }
  // 꺾은 선: 오른쪽으로 나가 내려가고 왼쪽으로 돌아 들어간다
  const rightX = sx + 20;
  const leftX = tx - 20;
  const down = ty >= sy;
  const midY =
    opts.midY ??
    (down
      ? Math.max(a.y + a.h + 24, (a.y + a.h + b.y) / 2)
      : Math.min(a.y - 30, ty + b.h / 2 + 40));
  const s = down ? 1 : -1;
  const d = [
    `M${String(sx)} ${String(sy)}`,
    `H${String(rightX - R)}`,
    `Q${String(rightX)} ${String(sy)} ${String(rightX)} ${String(sy + s * R)}`,
    `V${String(midY - s * R)}`,
    `Q${String(rightX)} ${String(midY)} ${String(rightX - R)} ${String(midY)}`,
    `H${String(leftX + R)}`,
    `Q${String(leftX)} ${String(midY)} ${String(leftX)} ${String(midY + s * R)}`,
    `V${String(ty - s * R)}`,
    `Q${String(leftX)} ${String(ty)} ${String(leftX + R)} ${String(ty)}`,
    `H${String(tx - 2)}`,
  ].join(' ');
  return { d, end: { x: tx, y: ty, dir: 'right' }, mid: { x: (rightX + leftX) / 2, y: midY } };
}

/** 위 → 아래 선(좁은 화면): 아래 가운데 → 위 가운데. 같은 줄(⑦ → ⑤)은 오른쪽 화살표. */
export function edgeVertical(a: Box, b: Box): EdgeGeom {
  if (Math.abs(a.y - b.y) < 4 || (b.y < a.y + a.h && b.x > a.x)) {
    const sx = a.x + a.w;
    const sy = a.y + a.h / 2;
    const tx = b.x;
    const ty = Math.min(b.y + b.h - 6, Math.max(b.y + 6, sy));
    if (Math.abs(ty - sy) < 2) {
      return {
        d: `M${String(sx)} ${String(sy)} L${String(tx - 2)} ${String(ty)}`,
        end: { x: tx, y: ty, dir: 'right' },
        mid: { x: (sx + tx) / 2, y: sy },
      };
    }
    const ex = tx - 6;
    return {
      d: `M${String(sx)} ${String(sy)} H${String(ex - R)} Q${String(ex)} ${String(sy)} ${String(ex)} ${String(sy - R)} V${String(b.y + b.h + 2)}`,
      end: { x: ex, y: b.y + b.h, dir: 'up' },
      mid: { x: ex, y: sy },
    };
  }
  const sx = a.x + a.w / 2;
  const sy = a.y + a.h;
  const tx = b.x + b.w / 2;
  const ty = b.y;
  const dy = Math.max(18, (ty - sy) / 2);
  return {
    d: `M${String(sx)} ${String(sy)} C${String(sx)} ${String(sy + dy)} ${String(tx)} ${String(ty - dy)} ${String(tx)} ${String(ty - 2)}`,
    end: { x: tx, y: ty, dir: 'down' },
    mid: { x: (sx + tx) / 2, y: (sy + ty) / 2 },
  };
}

export function arrowPath(end: EdgeGeom['end'], size = 5): string {
  const { x, y, dir } = end;
  if (dir === 'right')
    return `M${String(x - size)} ${String(y - size)} L${String(x)} ${String(y)} L${String(x - size)} ${String(y + size)}`;
  if (dir === 'down')
    return `M${String(x - size)} ${String(y - size)} L${String(x)} ${String(y)} L${String(x + size)} ${String(y - size)}`;
  return `M${String(x - size)} ${String(y + size)} L${String(x)} ${String(y)} L${String(x + size)} ${String(y + size)}`;
}

/** 점에서 선(경로 문자열 대신 표본점)까지 거리 — 끌어 온 조건을 놓을 선 찾기. */
export function samplePath(
  a: Box,
  b: Box,
  fromBelow = false,
  steps = 24,
  mid: number | null = null,
): { x: number; y: number }[] {
  if (fromBelow) {
    const x = b.x + b.w / 2;
    return Array.from({ length: steps + 1 }, (_, i) => ({
      x,
      y: a.y + ((b.y + b.h - a.y) * i) / steps,
    }));
  }
  const sx = a.x + a.w;
  const sy = a.y + a.h / 2;
  const tx = b.x;
  const ty = b.y + b.h / 2;
  if (tx >= sx + 24 || tx >= a.x + 8) {
    const dx = Math.max(tx >= sx + 24 ? 36 : 70, (tx - sx) / 2);
    const pts = [];
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const u = 1 - t;
      pts.push({
        x: u * u * u * sx + 3 * u * u * t * (sx + dx) + 3 * u * t * t * (tx - dx) + t * t * t * tx,
        y: u * u * u * sy + 3 * u * u * t * sy + 3 * u * t * t * ty + t * t * t * ty,
      });
    }
    return pts;
  }
  const rightX = sx + 20;
  const leftX = tx - 20;
  const down = ty >= sy;
  const midY =
    mid ??
    (down
      ? Math.max(a.y + a.h + 24, (a.y + a.h + b.y) / 2)
      : Math.min(a.y - 30, ty + b.h / 2 + 40));
  const corners = [
    { x: sx, y: sy },
    { x: rightX, y: sy },
    { x: rightX, y: midY },
    { x: leftX, y: midY },
    { x: leftX, y: ty },
    { x: tx, y: ty },
  ];
  const pts: { x: number; y: number }[] = [];
  for (let k = 0; k < corners.length - 1; k++) {
    const p = corners[k];
    const q = corners[k + 1];
    if (!p || !q) continue;
    for (let i = 0; i < 8; i++)
      pts.push({ x: p.x + ((q.x - p.x) * i) / 8, y: p.y + ((q.y - p.y) * i) / 8 });
  }
  pts.push({ x: tx, y: ty });
  return pts;
}

export function distanceTo(pts: { x: number; y: number }[], x: number, y: number): number {
  let best = Infinity;
  for (let i = 0; i < pts.length - 1; i++) {
    const p = pts[i];
    const q = pts[i + 1];
    if (!p || !q) continue;
    const vx = q.x - p.x;
    const vy = q.y - p.y;
    const len = vx * vx + vy * vy;
    const t = len === 0 ? 0 : Math.max(0, Math.min(1, ((x - p.x) * vx + (y - p.y) * vy) / len));
    const dx = p.x + t * vx - x;
    const dy = p.y + t * vy - y;
    best = Math.min(best, Math.sqrt(dx * dx + dy * dy));
  }
  return best;
}

/** ⑦ → ⑤ 선을 아래에서 곧게 올릴까(⑦이 ⑤ 바로 아래). */
export function weightFromBelow(w: Box, buy: Box): boolean {
  const cw = w.x + w.w / 2;
  return w.y > buy.y + buy.h && cw > buy.x && cw < buy.x + buy.w;
}

/** 조건에 붙는 이름표: '분기 · 하나라도'(나가는 선이 둘 이상) · '연결 · 모두'(같은 묶음 뒤에 이어서 연결). */
export function nodeTags(cat: RuleCatalog, g: Graph): Record<string, 'branch' | 'chain'> {
  const by = new Map(g.nodes.map((n) => [n.id, n]));
  const stage = (id: string) => stageOf(cat, by.get(id)?.piece ?? '');
  const out: Record<string, 'branch' | 'chain'> = {};
  const outs = outgoing(g);
  for (const n of g.nodes) {
    const s = stage(n.id);
    if (s === 'weight') continue;
    const nexts = (outs.get(n.id) ?? []).filter((d) => stage(d) !== 'weight');
    if (nexts.length >= 2) out[n.id] = 'branch';
  }
  const group = (s: SlotKey) =>
    s === 'signal' || s === 'filter' ? 'entry' : s === 'sell' ? 'sell' : '';
  for (const e of g.edges) {
    const a = stage(e.from);
    const b = stage(e.to);
    if (group(a) && group(a) === group(b) && out[e.to] === undefined) out[e.to] = 'chain';
  }
  return out;
}
