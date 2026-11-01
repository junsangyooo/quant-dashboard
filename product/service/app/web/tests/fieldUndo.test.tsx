// 지적 1: 숫자 칸은 늘 그래프 값을 보인다. 입력 → 되돌리기 → 칸 값 = 카드 값 = 저장 값.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { Catalog, Graph, ParamValue } from '../src/api/mvp';
import { pieceTitle } from '../src/graph/rules';
import { Field } from '../src/screens/Editor/Panel';
import { historyOf, push, redo, setParam, undo } from '../src/screens/Editor/model';

const fx = JSON.parse(
  readFileSync(join(process.cwd(), 'tests/fixtures/graph_cases.json'), 'utf8'),
) as {
  catalog: Pick<Catalog, 'pieces' | 'slots' | 'names'>;
};
const catalog = { ...fx.catalog, how: [] } as unknown as Catalog;
const start: Graph = {
  nodes: [{ id: 's1', piece: 'high_breakout', params: { n: null }, x: 0, y: 0 }],
  edges: [],
};

function Harness() {
  const [h, setH] = useState(() => historyOf(start));
  const node = h.now.nodes[0];
  if (!node) return null;
  return (
    <>
      <Field
        cat={catalog}
        catalog={catalog}
        node={node}
        pkey="n"
        focus={false}
        onChange={(k: string, v: ParamValue) => {
          setH(push(h, setParam(h.now, 's1', k, v), `p:s1:${k}`));
        }}
      />
      <span data-testid="card">{pieceTitle(catalog, node)}</span>
      <span data-testid="saved">{JSON.stringify(h.now.nodes[0]?.params)}</span>
      <button
        type="button"
        onClick={() => {
          setH(undo(h));
        }}
      >
        undo
      </button>
      <button
        type="button"
        onClick={() => {
          setH(redo(h));
        }}
      >
        redo
      </button>
      <button
        type="button"
        onClick={() => {
          setH(push(h, setParam(h.now, 's1', 'n', 60)));
        }}
      >
        other
      </button>
    </>
  );
}

describe('숫자 칸 = 카드 = 저장 값', () => {
  it('입력 → 되돌리기 → 다시 하기 → 다른 곳에서 값이 바뀜', () => {
    render(<Harness />);
    const input = screen.getByLabelText('기간');
    fireEvent.change(input, { target: { value: '20' } });
    expect((input as HTMLInputElement).value).toBe('20');
    expect(screen.getByTestId('card').textContent).toBe('20일 최고가 돌파');
    expect(screen.getByTestId('saved').textContent).toBe('{"n":20}');

    fireEvent.click(screen.getByText('undo'));
    expect((input as HTMLInputElement).value).toBe('');
    expect(screen.getByTestId('card').textContent).toBe('n일 최고가 돌파');
    expect(screen.getByTestId('saved').textContent).toBe('{"n":null}');

    fireEvent.click(screen.getByText('redo'));
    expect((input as HTMLInputElement).value).toBe('20');
    expect(screen.getByTestId('saved').textContent).toBe('{"n":20}');

    fireEvent.click(screen.getByText('other'));
    expect((input as HTMLInputElement).value).toBe('60');
    expect(screen.getByTestId('card').textContent).toBe('60일 최고가 돌파');
  });

  it('치던 글(쉼표)은 같은 값일 때 그대로 둔다', () => {
    render(<Harness />);
    const input = screen.getByLabelText('기간');
    fireEvent.change(input, { target: { value: '1,00' } });
    expect((input as HTMLInputElement).value).toBe('1,00');
    expect(screen.getByTestId('saved').textContent).toBe('{"n":100}');
  });
});
