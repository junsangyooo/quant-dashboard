// T-54: the 사용 조건 screen text (src/copy/terms.ts) is the same as the draft document
// (product/service/TERMS-DRAFT.md), has the seven SPEC 8-3 headings, and shows '법률 확인 전 초안'.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { termsCopy } from '../src/copy/terms';

const doc = readFileSync(join(process.cwd(), '..', '..', 'TERMS-DRAFT.md'), 'utf8');

function parse(md: string) {
  const out: { title: string; lines: string[] }[] = [];
  for (const raw of md.split('\n')) {
    const line = raw.trimEnd();
    if (line.startsWith('## ')) out.push({ title: line.slice(3), lines: [] });
    else if (line.startsWith('- ') && out.length) out[out.length - 1]?.lines.push(line.slice(2));
  }
  return out;
}

describe('사용 조건 초안', () => {
  it('marks the document and the screen as a draft before legal review', () => {
    expect(doc.split('\n')[0]).toContain('법률 확인 전 초안');
    expect(termsCopy.draft).toBe('법률 확인 전 초안');
  });

  it('has the seven SPEC 8-3 sections in order', () => {
    expect(termsCopy.sections.map((s) => s.title)).toEqual([
      '1. 개인 사용',
      '2. 투자 판단과 손익은 본인 몫',
      '3. 있는 그대로 제공',
      '4. 업데이트 약속 없음',
      '5. 지원 없음',
      '6. 시스템 위험',
      '7. 데이터 출처',
    ]);
  });

  it('screen text equals the document', () => {
    expect(termsCopy.sections.map((s) => ({ title: s.title, lines: [...s.lines] }))).toEqual(
      parse(doc),
    );
  });
});
