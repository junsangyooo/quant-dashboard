// Flow canvas geometry (규칙 AI 흐름). The engine sends cards on a 3-column grid (col/row) and the
// lines between them; the screen measures the cards and routes the lines.
// - grid (1100px up, Figma 1:62197): same-row lines run 60px below the card tops; lines to a lower
//   row leave the card bottom (two exits: '예' 48px left of centre, the other 62px right), turn
//   32px above the target row and enter the target top; ports are half-hidden 8px circles.
// - stack (390, Figma 1:61226): one column; lines run down a rail 28px in from the card edge,
//   exception cards sit indented with a stub from the rail, and a branch that skips cards takes a
//   detour lane 24px right of the cards.
import { ARROW } from '../../charts/geometry/deviation';
import { r2 } from '../../charts/geometry/scale';
import { edgeLabelOf, type EdgeLabel, type FlowEdge, type FlowNode } from './proposed';

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export type Boxes = ReadonlyMap<string, Box>;

export const FLOW = {
  hOffset: 60,
  turnAbove: 32,
  splitLeft: 48,
  splitRight: 62,
  corner: 8,
  labelGap: 8,
  labelH: 18,
  labelAbove: 6,
  rail: 28,
  lane: 24,
  laneStep: 14,
} as const;

export interface Pt {
  x: number;
  y: number;
}

export interface RoutedEdge {
  key: string;
  from: string;
  to: string;
  style: FlowEdge['style'];
  points: Pt[];
  d: string;
  /** Open arrowhead at the last point. */
  arrow: string;
  /** Start port (grid mode only). */
  port: Pt | null;
  label: {
    key: EdgeLabel;
    x: number;
    /** Vertical centre of the label line. */
    y: number;
    anchor: 'start' | 'middle' | 'end';
    /** Drawn over the line on a canvas-coloured box. */
    boxed: boolean;
  } | null;
}

// ── path helpers ────────────────────────────────────────────────────────────

/** Orthogonal polyline with rounded corners (quadratic, radius clamped to half a segment). */
export function roundedPath(points: readonly Pt[], radius: number = FLOW.corner): string {
  const [first] = points;
  if (!first) return '';
  let d = `M${String(r2(first.x))} ${String(r2(first.y))}`;
  for (let i = 1; i < points.length; i++) {
    const p = points[i];
    const prev = points[i - 1];
    const next = points[i + 1];
    if (!p || !prev) continue;
    if (!next) {
      d += `L${String(r2(p.x))} ${String(r2(p.y))}`;
      continue;
    }
    const inLen = Math.hypot(p.x - prev.x, p.y - prev.y);
    const outLen = Math.hypot(next.x - p.x, next.y - p.y);
    const r = Math.min(radius, inLen / 2, outLen / 2);
    if (r <= 0 || inLen === 0 || outLen === 0) {
      d += `L${String(r2(p.x))} ${String(r2(p.y))}`;
      continue;
    }
    const ax = p.x - ((p.x - prev.x) / inLen) * r;
    const ay = p.y - ((p.y - prev.y) / inLen) * r;
    const bx = p.x + ((next.x - p.x) / outLen) * r;
    const by = p.y + ((next.y - p.y) / outLen) * r;
    d += `L${String(r2(ax))} ${String(r2(ay))}Q${String(r2(p.x))} ${String(r2(p.y))} ${String(r2(bx))} ${String(r2(by))}`;
  }
  return d;
}

/** Open arrowhead ('>') at the end of the last segment. */
export function arrowHead(points: readonly Pt[]): string {
  const end = points.at(-1);
  const before = points.at(-2);
  if (!end || !before) return '';
  const len = Math.hypot(end.x - before.x, end.y - before.y) || 1;
  const ux = (end.x - before.x) / len;
  const uy = (end.y - before.y) / len;
  const bx = end.x - ux * ARROW.length;
  const by = end.y - uy * ARROW.length;
  const px = -uy * ARROW.spread;
  const py = ux * ARROW.spread;
  return [
    `${String(r2(bx + px))},${String(r2(by + py))}`,
    `${String(r2(end.x))},${String(r2(end.y))}`,
    `${String(r2(bx - px))},${String(r2(by - py))}`,
  ].join(' ');
}

function edgeKey(e: FlowEdge, i: number): string {
  return `${e.from}->${e.to}-${String(i)}`;
}

function finish(
  e: FlowEdge,
  i: number,
  points: Pt[],
  port: Pt | null,
  label: RoutedEdge['label'],
): RoutedEdge {
  return {
    key: edgeKey(e, i),
    from: e.from,
    to: e.to,
    style: e.style,
    points,
    d: roundedPath(points),
    arrow: arrowHead(points),
    port,
    label,
  };
}

// ── grid (1100px up) ───────────────────────────────────────────────────────

export function routeGrid(
  nodes: readonly FlowNode[],
  edges: readonly FlowEdge[],
  boxes: Boxes,
): RoutedEdge[] {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const downward = (e: FlowEdge) => {
    const a = byId.get(e.from);
    const b = byId.get(e.to);
    return a !== undefined && b !== undefined && b.row > a.row;
  };

  return edges.flatMap((e, i) => {
    const a = byId.get(e.from);
    const b = byId.get(e.to);
    const A = boxes.get(e.from);
    const B = boxes.get(e.to);
    if (!a || !b || !A || !B) return [];
    const key = edgeLabelOf(e);

    if (a.row === b.row) {
      const y = Math.min(A.y, B.y) + FLOW.hOffset;
      const forward = b.col >= a.col;
      const x1 = forward ? A.x + A.w : A.x;
      const x2 = forward ? B.x : B.x + B.w;
      const label = key
        ? {
            key,
            x: (x1 + x2) / 2,
            y: y - FLOW.labelAbove - FLOW.labelH / 2,
            anchor: 'middle' as const,
            boxed: true,
          }
        : null;
      return [
        finish(
          e,
          i,
          [
            { x: x1, y },
            { x: x2, y },
          ],
          { x: x1, y },
          label,
        ),
      ];
    }

    if (b.row > a.row) {
      const exits = edges.filter((o) => o.from === e.from && downward(o));
      const cx = A.x + A.w / 2;
      let ex = cx;
      if (exits.length >= 2) {
        ex = key === 'yes' ? cx - FLOW.splitLeft : cx + FLOW.splitRight;
      }
      const exitY = A.y + A.h;
      const straight = ex >= B.x && ex <= B.x + B.w && a.col === b.col;
      let points: Pt[];
      if (straight) {
        points = [
          { x: ex, y: exitY },
          { x: ex, y: B.y },
        ];
      } else {
        const turnY = B.y - FLOW.turnAbove;
        const enter = B.x + B.w / 2;
        points = [
          { x: ex, y: exitY },
          { x: ex, y: turnY },
          { x: enter, y: turnY },
          { x: enter, y: B.y },
        ];
      }
      const segEnd = points[1]?.y ?? exitY;
      const label = key
        ? key === 'yes'
          ? {
              key,
              x: ex + FLOW.labelGap,
              y: (exitY + segEnd) / 2,
              anchor: 'start' as const,
              boxed: false,
            }
          : { key, x: ex, y: (exitY + segEnd) / 2, anchor: 'middle' as const, boxed: true }
        : null;
      return [finish(e, i, points, { x: ex, y: exitY }, label)];
    }

    // Upward (not drawn in Figma): leave the top, turn 32px above the source, enter the bottom.
    const cx = A.x + A.w / 2;
    const turnY = A.y - FLOW.turnAbove;
    const enter = B.x + B.w / 2;
    const points = [
      { x: cx, y: A.y },
      { x: cx, y: turnY },
      { x: enter, y: turnY },
      { x: enter, y: B.y + B.h },
    ];
    return [finish(e, i, points, { x: cx, y: A.y }, null)];
  });
}

// ── stack (below 1100px) ───────────────────────────────────────────────────

/** Reading order of the 390 column: by row then column, each 예외 card right after its source. */
export function stackOrder(nodes: readonly FlowNode[], edges: readonly FlowEdge[]): string[] {
  const sorted = [...nodes].sort((p, q) => p.row - q.row || p.col - q.col);
  const exceptions = sorted.filter((n) => n.type === 'exception');
  const order = sorted.filter((n) => n.type !== 'exception').map((n) => n.id);
  for (const ex of exceptions) {
    const source = edges.find((e) => e.to === ex.id)?.from;
    const at = source ? order.indexOf(source) : -1;
    if (at === -1) order.push(ex.id);
    else order.splice(at + 1, 0, ex.id);
  }
  return order;
}

export type StackGap = 'first' | 'default' | 'label' | 'exception' | 'afterException';

/** Space above each card of the 390 column (Figma 1:61226: 28, 44 with a branch word, 16 / 24). */
export function stackGaps(
  order: readonly string[],
  nodes: readonly FlowNode[],
  edges: readonly FlowEdge[],
): Map<string, StackGap> {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const gaps = new Map<string, StackGap>();
  order.forEach((id, i) => {
    const prev = order[i - 1];
    if (prev === undefined) gaps.set(id, 'first');
    else if (byId.get(id)?.type === 'exception') gaps.set(id, 'exception');
    else if (byId.get(prev)?.type === 'exception') gaps.set(id, 'afterException');
    else {
      const edge = edges.find((e) => e.from === prev && e.to === id);
      gaps.set(id, edge && edgeLabelOf(edge) ? 'label' : 'default');
    }
  });
  return gaps;
}

export function routeStack(
  order: readonly string[],
  nodes: readonly FlowNode[],
  edges: readonly FlowEdge[],
  boxes: Boxes,
): RoutedEdge[] {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const index = new Map(order.map((id, i) => [id, i]));
  const isException = (id: string) => byId.get(id)?.type === 'exception';
  const main = order.filter((id) => !isException(id)).flatMap((id) => boxes.get(id) ?? []);
  const left = Math.min(...main.map((b) => b.x));
  const right = Math.max(...main.map((b) => b.x + b.w));
  const rail = left + FLOW.rail;
  const nextTop = (id: string) => {
    const i = index.get(id);
    const next = i === undefined ? undefined : order[i + 1];
    return next === undefined ? undefined : boxes.get(next)?.y;
  };
  let lanes = 0;

  return edges.flatMap((e, i) => {
    const ia = index.get(e.from);
    const ib = index.get(e.to);
    const A = boxes.get(e.from);
    const B = boxes.get(e.to);
    if (ia === undefined || ib === undefined || !A || !B) return [];
    const key = edgeLabelOf(e);
    const gapMid = (A.y + A.h + (nextTop(e.from) ?? A.y + A.h + 28)) / 2;

    if (isException(e.to)) {
      const midY = B.y + B.h / 2;
      const passes = edges.some(
        (o) => o !== e && o.from === e.from && (index.get(o.to) ?? -1) > ib,
      );
      const points = passes
        ? [
            { x: rail, y: midY },
            { x: B.x, y: midY },
          ]
        : [
            { x: rail, y: A.y + A.h },
            { x: rail, y: midY },
            { x: B.x, y: midY },
          ];
      return [finish(e, i, points, null, null)];
    }

    const between = order.slice(ia + 1, ib);
    if (ib > ia && between.every(isException)) {
      const points = [
        { x: rail, y: A.y + A.h },
        { x: rail, y: B.y },
      ];
      const label = key
        ? { key, x: rail + FLOW.labelGap, y: gapMid, anchor: 'start' as const, boxed: false }
        : null;
      return [finish(e, i, points, null, label)];
    }

    const laneX = right + FLOW.lane + lanes * FLOW.laneStep;
    lanes += 1;
    const ay = A.y + A.h / 2;
    const by = B.y + B.h / 2;
    const points = [
      { x: A.x + A.w, y: ay },
      { x: laneX, y: ay },
      { x: laneX, y: by },
      { x: B.x + B.w, y: by },
    ];
    const label = key
      ? { key, x: laneX - FLOW.labelGap, y: gapMid, anchor: 'end' as const, boxed: false }
      : null;
    return [finish(e, i, points, null, label)];
  });
}
