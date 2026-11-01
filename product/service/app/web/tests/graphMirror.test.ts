// 화면의 그래프 검사(src/graph/rules.ts)가 서버(app/graph.py)와 같은 결과를 내는지: 서버가 만든 대조 파일
// (tests/fixtures/graph_cases.json · mvp/tests/regression/graph_cases.py --write)과 그래프마다 견준다.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { Analysis, Graph, PieceSpec, SlotInfo } from '../src/api/mvp';
import { addReason, analyze, edgeReason } from '../src/graph/rules';

interface Case {
  graph: Graph;
  analysis: Analysis;
  edges: [string, string, string | null][];
  adds: Record<string, string | null>;
}

const data = JSON.parse(
  readFileSync(join(process.cwd(), 'tests/fixtures/graph_cases.json'), 'utf8'),
) as {
  catalog: { pieces: Record<string, PieceSpec>; slots: SlotInfo[]; names: Record<string, string> };
  cases: Case[];
};

describe('graph checks mirror the server', () => {
  it('has many cases', () => {
    expect(data.cases.length).toBeGreaterThan(200);
  });

  it('analyze() is the same for every graph', () => {
    const diffs: number[] = [];
    data.cases.forEach((c, i) => {
      const got = analyze(data.catalog, c.graph);
      if (JSON.stringify(sortKeys(got)) !== JSON.stringify(sortKeys(c.analysis))) diffs.push(i);
    });
    if (diffs.length > 0) {
      const i = diffs[0] ?? 0;
      const c = data.cases[i];
      if (c) expect(analyze(data.catalog, c.graph)).toEqual(c.analysis);
    }
    expect(diffs).toEqual([]);
  });

  it('edgeReason() and addReason() are the same', () => {
    for (const c of data.cases) {
      for (const [a, b, why] of c.edges) expect(edgeReason(data.catalog, c.graph, a, b)).toBe(why);
      for (const [piece, why] of Object.entries(c.adds))
        expect(addReason(data.catalog, c.graph, piece)).toBe(why);
    }
  });
});

function sortKeys(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(sortKeys);
  if (v && typeof v === 'object')
    return Object.fromEntries(
      Object.entries(v as Record<string, unknown>)
        .sort(([a], [b]) => (a < b ? -1 : 1))
        .map(([k, x]) => [k, sortKeys(x)]),
    );
  return v;
}
