import { describe, expect, it } from 'vitest';
import type { Body, Graph, ParamSpec } from '../src/api/mvp';
import { fieldProblem, rangeText } from '../src/graph/rules';
import {
  changeCount,
  changes,
  historyOf,
  parseNumber,
  parseSymbols,
  push,
  redo,
  removeNode,
  splitEdge,
  undo,
} from '../src/screens/Editor/model';

const pct: ParamSpec = { key: 'pct', label: '손절', unit: '%', min: 1, max: 50, integer: false };
const days: ParamSpec = {
  key: 'n',
  label: '보유 기간',
  unit: '거래일',
  min: 1,
  max: 250,
  integer: true,
};
const syms: ParamSpec = { key: 'symbols', label: '종목 코드', kind: 'symbols', min: 1, max: 30 };

describe('field checks mirror app/graph.py field_problem()', () => {
  it('blank · range · integer · not a number', () => {
    expect(fieldProblem(pct, null)?.[0]).toBe('blank');
    expect(fieldProblem(pct, 60)).toEqual(['range', '손절은 1~50% 사이로 입력해 주세요']);
    expect(fieldProblem(pct, 5)).toBeNull();
    expect(fieldProblem(days, 2.5)).toEqual(['range', '보유 기간은 정수로 입력해 주세요']);
    expect(fieldProblem(days, 'abc')?.[0]).toBe('range');
  });

  it('symbols: blank, six digits, at most max', () => {
    expect(fieldProblem(syms, [])).toEqual(['blank', '종목 코드를 입력해 주세요']);
    expect(fieldProblem(syms, ['5930'])?.[0]).toBe('range');
    expect(fieldProblem(syms, ['005930', '000660'])).toBeNull();
  });

  it('parses typed text like the server does', () => {
    expect(parseNumber('')).toBeNull();
    expect(parseNumber('1,000')).toBe(1000);
    expect(parseNumber('abc')).toBe('abc');
    expect(parseSymbols('005930, 000660.KS  005930')).toEqual(['005930', '000660']);
  });

  it('writes the allowed range like the server', () => {
    expect(rangeText({ ...pct, min: 0.1, max: 100000, unit: '억 원' })).toBe('0.1~100,000억 원');
    expect(rangeText(pct)).toBe('1~50%');
  });
});

const g: Graph = {
  nodes: [
    { id: 'u1', piece: 'manual_list', params: { symbols: ['005930'] }, x: 0, y: 0 },
    { id: 'k1', piece: 'top_n', params: { n: null }, x: 200, y: 0 },
    { id: 'b1', piece: 'next_open', params: {}, x: 400, y: 0 },
  ],
  edges: [
    { from: 'u1', to: 'k1' },
    { from: 'k1', to: 'b1' },
  ],
};

describe('graph edits · history · leave summary', () => {
  it('split puts the new condition on the line, delete takes its lines', () => {
    const s = splitEdge(
      g,
      { from: 'u1', to: 'k1' },
      { id: 's1', piece: 'ma_cross_up', params: { n: null }, x: 100, y: 0 },
    );
    expect(s.edges).toEqual([
      { from: 'u1', to: 's1' },
      { from: 's1', to: 'k1' },
      { from: 'k1', to: 'b1' },
    ]);
    const r = removeNode(s, 's1');
    expect(r.lines).toBe(2);
    expect(r.graph.edges).toEqual([{ from: 'k1', to: 'b1' }]); // 앞뒤를 저절로 잇지 않는다
  });

  it('undo · redo · typing in one box is one step', () => {
    let h = historyOf(g);
    const a = { ...g, edges: [] };
    h = push(h, a);
    h = push(h, { ...a, nodes: [] }, 'p:k1:n');
    h = push(h, { ...a, nodes: [] }, 'p:k1:n');
    expect(h.past.length).toBe(2);
    h = undo(h);
    expect(h.now).toBe(a);
    h = redo(h);
    expect(h.now.nodes).toEqual([]);
  });

  it('counts what changed since the saved version', () => {
    const saved: Body = { name: 'a', graph: g };
    expect(changeCount(changes(saved, { name: 'a', graph: g }))).toBe(0);
    const next = removeNode(g, 'k1').graph;
    const c = changes(saved, { name: 'a', graph: next });
    expect(c.removed).toBe(1);
    expect(c.lines).toBe(0);
  });
});
