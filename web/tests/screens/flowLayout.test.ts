// Flow line routing against the Figma frames: [예시] 종목 모멘텀 1440 (1:62197, canvas coordinates)
// and 390 (1:61226). Card boxes are the Figma ones; the routed points must land on the drawn lines.
import { describe, expect, it } from 'vitest';
import { ruleMomentum } from '../../src/fixtures/parts/rules';
import type { FlowDisplay } from '../../src/api/types';
import {
  arrowHead,
  roundedPath,
  routeGrid,
  routeStack,
  stackGaps,
  stackOrder,
  type Box,
} from '../../src/screens/Rules/flowLayout';

const flow = ruleMomentum().display as FlowDisplay;

/** 1:62197 '캔버스' children (x, y, w, h). */
const GRID_BOXES = new Map<string, Box>([
  ['start', { x: 40, y: 40, w: 236, h: 160 }],
  ['stock', { x: 330, y: 40, w: 236, h: 236 }],
  ['data', { x: 620, y: 40, w: 236, h: 204 }],
  ['ai', { x: 40, y: 348, w: 236, h: 229 }],
  ['weight', { x: 330, y: 348, w: 236, h: 206 }],
  ['condition', { x: 620, y: 348, w: 236, h: 198 }],
  ['action', { x: 40, y: 649, w: 236, h: 204 }],
  ['result', { x: 620, y: 649, w: 236, h: 192 }],
  ['exception', { x: 40, y: 909, w: 236, h: 202 }],
]);

function edge(from: string, to: string) {
  const routed = routeGrid(flow.nodes, flow.edges, GRID_BOXES);
  const e = routed.find((r) => r.from === from && r.to === to);
  if (!e) throw new Error(`no edge ${from}→${to}`);
  return e;
}

describe('grid routing (1440, 1:62197)', () => {
  it('same-row lines run 60px below the card tops, from the right edge to the next left edge', () => {
    expect(edge('start', 'stock').points).toEqual([
      { x: 276, y: 100 },
      { x: 330, y: 100 },
    ]);
    expect(edge('stock', 'data').points).toEqual([
      { x: 566, y: 100 },
      { x: 620, y: 100 },
    ]);
    expect(edge('start', 'stock').port).toEqual({ x: 276, y: 100 });
    // action → result skips the empty middle column (Figma '연결선' 344×0 @276,709).
    expect(edge('action', 'result').points).toEqual([
      { x: 276, y: 709 },
      { x: 620, y: 709 },
    ]);
  });

  it('a line to the next row leaves the bottom centre and turns 32px above the target row', () => {
    // Figma: M 580 0 L 580 72 L 0 72 L 0 104 at (158, 244) → 738,244 → 738,316 → 158,316 → 158,348.
    expect(edge('data', 'ai').points).toEqual([
      { x: 738, y: 244 },
      { x: 738, y: 316 },
      { x: 158, y: 316 },
      { x: 158, y: 348 },
    ]);
  });

  it('two exits under 조건: 예 48px left of centre (dashed), 아니오 · 그대로 62px right, straight down', () => {
    const yes = edge('condition', 'action');
    expect(yes.style).toBe('not-taken');
    expect(yes.points[0]).toEqual({ x: 690, y: 546 });
    expect(yes.points.at(-1)).toEqual({ x: 158, y: 649 });
    expect(yes.label).toMatchObject({ key: 'yes', x: 698, anchor: 'start', boxed: false });
    const no = edge('condition', 'result');
    expect(no.style).toBe('taken');
    expect(no.points).toEqual([
      { x: 800, y: 546 },
      { x: 800, y: 649 },
    ]);
    expect(no.label).toMatchObject({
      key: 'no-keep',
      x: 800,
      y: 597.5,
      anchor: 'middle',
      boxed: true,
    });
  });

  it('예외 is a dotted line straight down from 행동 (Figma dash [2, 3])', () => {
    const ex = edge('action', 'exception');
    expect(ex.style).toBe('exception');
    expect(ex.points).toEqual([
      { x: 158, y: 853 },
      { x: 158, y: 909 },
    ]);
  });
});

describe('stack routing (390, 1:61226)', () => {
  it('reads by row and column with 예외 right after its source', () => {
    expect(stackOrder(flow.nodes, flow.edges)).toEqual([
      'start',
      'stock',
      'data',
      'ai',
      'weight',
      'condition',
      'action',
      'exception',
      'result',
    ]);
  });

  it('gaps: 28 between cards, 44 under a branch word, 16 / 24 around the indented 예외', () => {
    const order = stackOrder(flow.nodes, flow.edges);
    expect([...stackGaps(order, flow.nodes, flow.edges).values()]).toEqual([
      'first',
      'default',
      'default',
      'default',
      'default',
      'default',
      'label',
      'exception',
      'afterException',
    ]);
  });

  it('runs down a rail 28px in, detours right of the cards for the skipped 결과, stubs into 예외', () => {
    // Figma 1:61226 '흐름' children: cards at x 16 (290 wide), 예외 at x 72 (234 wide).
    const boxes = new Map<string, Box>([
      ['start', { x: 16, y: 16, w: 290, h: 160 }],
      ['stock', { x: 16, y: 204, w: 290, h: 236 }],
      ['data', { x: 16, y: 468, w: 290, h: 204 }],
      ['ai', { x: 16, y: 700, w: 290, h: 229 }],
      ['weight', { x: 16, y: 957, w: 290, h: 206 }],
      ['condition', { x: 16, y: 1191, w: 290, h: 198 }],
      ['action', { x: 16, y: 1433, w: 290, h: 204 }],
      ['exception', { x: 72, y: 1653, w: 234, h: 202 }],
      ['result', { x: 16, y: 1879, w: 290, h: 192 }],
    ]);
    const order = stackOrder(flow.nodes, flow.edges);
    const routed = routeStack(order, flow.nodes, flow.edges, boxes);
    const get = (from: string, to: string) => routed.find((r) => r.from === from && r.to === to);
    expect(get('start', 'stock')?.points).toEqual([
      { x: 44, y: 176 },
      { x: 44, y: 204 },
    ]);
    expect(get('condition', 'action')?.label).toMatchObject({ key: 'yes', x: 52, anchor: 'start' });
    // Figma: M 0 0 L 24 0 L 24 685 L 0 685 at (306, 1290).
    expect(get('condition', 'result')?.points).toEqual([
      { x: 306, y: 1290 },
      { x: 330, y: 1290 },
      { x: 330, y: 1975 },
      { x: 306, y: 1975 },
    ]);
    expect(get('condition', 'result')?.label).toMatchObject({
      key: 'no-keep',
      x: 322,
      anchor: 'end',
    });
    // 행동 → 결과 passes the indented 예외 on the rail; 행동 → 예외 is a stub from the rail.
    expect(get('action', 'result')?.points).toEqual([
      { x: 44, y: 1637 },
      { x: 44, y: 1879 },
    ]);
    expect(get('action', 'exception')?.points).toEqual([
      { x: 44, y: 1754 },
      { x: 72, y: 1754 },
    ]);
  });
});

describe('path helpers', () => {
  it('rounds the corners of an orthogonal path and keeps the end points', () => {
    const d = roundedPath([
      { x: 0, y: 0 },
      { x: 0, y: 72 },
      { x: -580, y: 72 },
    ]);
    expect(d).toBe('M0 0L0 64Q0 72 -8 72L-580 72');
  });

  it('draws an open arrowhead 5px back, ±4.5px across', () => {
    expect(
      arrowHead([
        { x: 0, y: 0 },
        { x: 0, y: 10 },
      ]),
    ).toBe('-4.5,5 0,10 4.5,5');
  });
});
