// Forbidden screen words: product/service/GLOSSARY.md §5 + SPEC 8-1 left column (TASKS T-01 · T-71).
// The list lives in forbiddenWords.json, made from those docs by app/tests/words_rules.py
// (app/tests/test_copytext.py fails when the JSON and the docs differ).
// Check shape (GLOSSARY §5): blank out the allowed forms first, then count what is left.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

interface WordRule {
  word: string;
  pattern: string;
  except: string[];
  source: string;
}

export interface ForbiddenRules {
  words: WordRule[];
  chips: string[];
  headerChips: string[];
}

export const RULES: ForbiddenRules = JSON.parse(
  readFileSync(join(process.cwd(), 'tests', 'forbiddenWords.json'), 'utf8'),
) as ForbiddenRules;

/** Every forbidden word in `text` as 'word: …context…'. */
export function forbiddenHits(text: string, rules: ForbiddenRules = RULES): string[] {
  const hits: string[] = [];
  for (const rule of rules.words) {
    let cleaned = text;
    for (const ok of rule.except) cleaned = cleaned.split(ok).join('\u0000'.repeat(ok.length));
    for (const m of cleaned.matchAll(new RegExp(rule.pattern, 'g'))) {
      const ctx = cleaned
        .slice(Math.max(0, m.index - 10), m.index + m[0].length + 10)
        .replaceAll('\u0000', '·')
        .replaceAll('\n', ' ');
      hits.push(`${rule.word}: …${ctx}…`);
    }
  }
  return hits;
}

/** Screen text in a source file: string literals and JSX text, with comments removed. */
export function screenText(code: string): string[] {
  const noComments = code.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"`\\])\/\/.*$/gm, '$1');
  const strings = [...noComments.matchAll(/(['"`])((?:\\.|(?!\1)[^\\])*)\1/g)].map(
    (m) => m[2] ?? '',
  );
  const jsx = [...noComments.matchAll(/>([^<>{}]*[가-힣][^<>{}]*)</g)].map((m) => m[1] ?? '');
  return [...strings, ...jsx];
}

/** String literals that are exactly a forbidden chip text ('예시'). */
export function chipHits(code: string, rules: ForbiddenRules = RULES): string[] {
  return screenText(code).filter((s) => rules.chips.includes(s));
}
