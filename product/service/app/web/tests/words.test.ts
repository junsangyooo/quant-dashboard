// Forbidden screen words (product/service/GLOSSARY.md §5 + SPEC 8-1) in the screen code (src/**)
// and the build output (dist/**). TASKS T-01 counts today's MVP hits; T-71 brings them to 0.
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';
import { chipHits, forbiddenHits, RULES, screenText } from './forbiddenWords';

const root = process.cwd();
const src = join(root, 'src');
const dist = join(root, 'dist');

// Today's MVP hits (T-01). The test fails if a change adds more; T-71 sets these to 0.
const SRC_HITS_LIMIT = 0;
const DIST_HITS_LIMIT = 0;

function walk(dir: string, exts: string[]): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p, exts));
    else if (exts.some((e) => p.endsWith(e))) out.push(p);
  }
  return out.sort();
}

function srcHits(): string[] {
  const hits: string[] = [];
  for (const f of walk(src, ['.ts', '.tsx'])) {
    // Fixtures never ship (vite.config.ts refuses them in a production build).
    if (f.includes(join('src', 'fixtures'))) continue;
    const code = readFileSync(f, 'utf8');
    const name = relative(root, f);
    for (const text of screenText(code))
      hits.push(...forbiddenHits(text).map((h) => `${name}: ${h}`));
    hits.push(...chipHits(code).map((c) => `${name}: chip '${c}'`));
  }
  // Header chip '모의투자' (GLOSSARY §5): the header must not render the paper mode badge.
  const header = readFileSync(join(src, 'components', 'Header.tsx'), 'utf8');
  if (header.includes('<ModeBadge'))
    hits.push(`src/components/Header.tsx: header chip '${RULES.headerChips[0] ?? ''}'`);
  return hits;
}

function distHits(): string[] {
  const hits: string[] = [];
  for (const f of walk(dist, ['.js', '.html'])) {
    const name = relative(root, f);
    hits.push(...forbiddenHits(readFileSync(f, 'utf8')).map((h) => `${name}: ${h}`));
  }
  return hits;
}

describe('forbidden screen words', () => {
  it('reads the GLOSSARY list', () => {
    expect(RULES.words.length).toBeGreaterThan(70);
    expect(RULES.chips).toEqual(['예시']);
    expect(RULES.headerChips).toEqual(['모의투자']);
  });

  it('catches the words and keeps the allowed forms', () => {
    const words = (t: string) => forbiddenHits(t).map((h) => h.split(': …')[0]);
    expect(words('조각 추가 · 블록 · 전략 코드 복사 · 값 넣기').sort()).toEqual(
      ['넣기', '블록', '전략 코드', '조각'].sort(),
    );
    expect(
      words(
        '빈칸 4개 · 붙여 넣기 · 투자 판단과 손익 · 숫자 칸 · 입력 칸 · 백테스트 · 시험 보내기 · 리포트',
      ),
    ).toEqual([]);
    expect(words('11/3 16:30 기준')).toEqual(['10/29 16:30 기준']);
    expect(words('실전 운용이나 모의투자 기록이 있는 전략은 삭제할 수 없어요')).toEqual([]);
  });

  it('reads screen text: literals and JSX text, not comments', () => {
    const code =
      "// 블록 주석\nconst a = '조각';\n/* 노드 */\nconst b = <p>칸 하나</p>;\nconst url = 'https://x';";
    expect(screenText(code)).toEqual(['조각', 'https://x', '칸 하나']);
    expect(chipHits("const c = { chip: '예시', name: '예시 전략' };")).toEqual(['예시']);
  });

  it(`screen code has at most ${SRC_HITS_LIMIT} hits (T-71: 0)`, () => {
    const hits = srcHits();
    console.log(`screen code forbidden words: ${hits.length}\n  ${hits.join('\n  ')}`);
    expect(hits.length).toBeLessThanOrEqual(SRC_HITS_LIMIT);
  });

  it.runIf(existsSync(join(dist, 'index.html')))(
    `build output has at most ${DIST_HITS_LIMIT} hits (T-71: 0)`,
    () => {
      const hits = distHits();
      console.log(`build output forbidden words: ${hits.length}\n  ${hits.join('\n  ')}`);
      expect(hits.length).toBeLessThanOrEqual(DIST_HITS_LIMIT);
    },
  );
});
