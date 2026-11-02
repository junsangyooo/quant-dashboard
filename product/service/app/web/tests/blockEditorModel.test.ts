// 편집기 v2 모델(T-30): 선 잇기 이유가 서버(app/blocks.py)와 같은 글 · 새 전략 꼴 · ⑥ → ⑥ 옮기기 · 조사.
import { describe, expect, it } from 'vitest';
import {
  addBlockReason,
  blankBody,
  connect,
  edgeReason,
  History,
  isSellChain,
  josaRo,
  mergeSell,
  newBlock,
  withBlock,
} from '../src/screens/BlockEditor/model';

describe('block editor model', () => {
  it('new strategy is ① → ④ → ⑤ ← ⑦ (그림 V2-23 빈 캔버스)', () => {
    const b = blankBody('새 전략');
    expect(b.graph.blocks.map((x) => x.stage)).toEqual(['universe', 'select', 'buy', 'weight']);
    expect(b.graph.blocks[2]?.rows[0]?.value).toBe(1); // 판 뒤 다시 사지 않는 기간 1거래일(R-G7)
    expect(b.graph.edges).toEqual([
      { from: 'u1', to: 'k1' },
      { from: 'k1', to: 'b1' },
      { from: 'w1', to: 'b1' },
    ]);
  });

  it('link reasons match the server text (R-G12)', () => {
    let b = blankBody();
    b = withBlock(b, newBlock(b.graph.blocks, 'signal'));
    b = withBlock(b, newBlock(b.graph.blocks, 'sell'));
    expect(edgeReason(b, 's1', 'b1')).toBe('종목 선정 단계는 매수 단계 바로 앞에 하나만 놓아요');
    expect(edgeReason(b, 'x1', 's1')).toBe('매도 단계는 매수 단계 뒤에 이어요');
    expect(edgeReason(b, 'k1', 'u1')).toBe('유니버스 단계 앞에는 다른 단계를 연결할 수 없어요');
    expect(edgeReason(b, 'u1', 'k1')).toBe('이미 연결돼 있어요');
    expect(edgeReason(b, 'b1', 'x1')).toBeNull();
    expect(addBlockReason(b.graph.blocks, 'weight', '비중')).toBe(
      '비중 단계는 하나만 놓을 수 있어요',
    );
  });

  it('⑥ → ⑥ asks first and can move rows into one stage', () => {
    let b = blankBody();
    b = withBlock(b, newBlock(b.graph.blocks, 'sell'));
    b = withBlock(b, newBlock(b.graph.blocks, 'sell'));
    b = connect(b, 'b1', 'x1');
    expect(isSellChain(b, 'x1', 'x2')).toBe(true);
    const merged = mergeSell(b, 'x1', 'x2');
    expect(merged.graph.blocks.filter((x) => x.stage === 'sell')).toHaveLength(1);
  });

  it('undo and redo', () => {
    const h = new History();
    const a = blankBody('a');
    const b = blankBody('b');
    h.push(a);
    expect(h.undo(b)?.name).toBe('a');
    expect(h.redo(a)?.name).toBe('b');
  });

  it('josa for version numbers (GLOSSARY 1절)', () => {
    expect([1, 3, 4, 6, 10, 13].map((n) => `${String(n)}${josaRo(n)}`)).toEqual([
      '1로',
      '3으로',
      '4로',
      '6으로',
      '10으로',
      '13으로',
    ]);
  });
});
