// The screen words (src/copy.ts · src/copy/*.ts) use the word rules in product/service/GLOSSARY.md (§3 · §4).
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { oldWordHits } from './oldWords';

const src = join(process.cwd(), 'src');
const files = [
  join(src, 'copy.ts'),
  ...readdirSync(join(src, 'copy')).map((f) => join(src, 'copy', f)),
];

/** String literals only (comments may name the old words). */
function literals(code: string): string {
  const noComments = code.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
  return [...noComments.matchAll(/(['"`])((?:\\.|(?!\1)[^\\])*)\1/g)].map((m) => m[2]).join('\n');
}

describe('screen words', () => {
  it('found the copy files', () => {
    expect(files.length).toBeGreaterThan(5);
  });

  for (const f of files) {
    it(`${f.slice(src.length + 1)} has no old words`, () => {
      expect(oldWordHits(literals(readFileSync(f, 'utf8')))).toEqual([]);
    });
  }

  it('the rule catches the old words', () => {
    expect(
      oldWordHits('조각 추가 · 판단 돌리기 · 칸 확인 · 틀 고르기 · 전략 코드 복사'),
    ).toHaveLength(6);
    expect(oldWordHits('빈칸 4개 · 붙여 넣기 · 투자 판단과 손익 · 틀려도 · 숫자 칸')).toEqual([]);
  });
});
