// 조사 고르기: 앞말(숫자 포함)의 받침에 따라. lib/format의 endsWithConsonant를 쓴다.
import { endsWithConsonant } from '../lib/format';

/** 받침이 ㄹ인가('1' 일 · '7' 칠 · '8' 팔 · '길'). (으)로는 ㄹ 받침 뒤에서 '로'다. */
function endsWithRieul(text: string): boolean {
  const last = text.trim().at(-1) ?? '';
  if (/[0-9]/.test(last)) return '178'.includes(last);
  const code = last.charCodeAt(0);
  return code >= 0xac00 && code <= 0xd7a3 && (code - 0xac00) % 28 === 8;
}

export type Particle = '으로' | '은' | '과' | '이' | '을';

/** `with('버전 3', '으로')` → '버전 3으로', `with('버전 2', '으로')` → '버전 2로'. */
export function withParticle(word: string, p: Particle): string {
  const closed = endsWithConsonant(word);
  switch (p) {
    case '으로':
      return word + (closed && !endsWithRieul(word) ? '으로' : '로');
    case '은':
      return word + (closed ? '은' : '는');
    case '과':
      return word + (closed ? '과' : '와');
    case '이':
      return word + (closed ? '이' : '가');
    case '을':
      return word + (closed ? '을' : '를');
  }
}

/** '버전 n' + 조사. */
export const version = (n: number, p: Particle) => withParticle(`버전 ${String(n)}`, p);

/** 조사 짝(graph/rules.ts josa): 앞말 받침에 따라 앞 것 또는 뒤 것. */
export const J = { iga: '이/가', eun: '은/는', eul: '을/를', gwa: '과/와', ro: '으로/로' } as const;
export type JosaPair = (typeof J)[keyof typeof J];
