// 조사 견본(TASKS P1-03 · P1-11: 조사는 견본만 얼리고 합치지 않음 · 합치는 것은 3단계).
// 지운 tests/particles.test.ts(src/copy/particles.ts · src/copy/editor.ts · src/graph/rules.ts josa의 시험)에 있던
// 버전 1 · 2 · 3 · 10 기대값을 글자 그대로 얼려 둔다. 조사 함수는 지워졌으므로 남아 있는 조사 코드 둘로만 견준다:
// - src/lib/format.ts endsWithConsonant: 받침 판정(particles.ts가 쓰던 함수 · 은/는 · 과/와 · 이/가 · 을/를).
// - src/screens/BlockEditor/model.ts josaRo: '버전 n' 뒤 (으)로(지금 화면이 쓰는 것 · 끝자리 3 · 6 · 0은 으로).
import { describe, expect, it } from 'vitest';
import { endsWithConsonant } from '../src/lib/format';
import { josaRo } from '../src/screens/BlockEditor/model';

/** '버전 n' + (으)로 저장(editorCopy.save · 1 · 2 · 3 · 10). */
const SAVE = {
  1: '버전 1로 저장',
  2: '버전 2로 저장',
  3: '버전 3으로 저장',
  10: '버전 10으로 저장',
} as const;

/** '버전 n' + 은/는 · 과/와(version(n, p)). */
const EUN = { 1: '버전 1은', 2: '버전 2는', 3: '버전 3은', 10: '버전 10은' } as const;
const GWA = { 1: '버전 1과', 2: '버전 2와', 3: '버전 3과', 10: '버전 10과' } as const;

/** withParticle · editorCopy 견본. */
const WITH: readonly { word: string; pair: readonly [string, string]; expected: string }[] = [
  { word: '버전 2', pair: ['이', '가'], expected: '버전 2가' },
  { word: '버전 3', pair: ['을', '를'], expected: '버전 3을' },
];
const LEAVE_BODY = '저장하지 않은 변경이 사라져요 · 조건 삭제 1 · 버전 1은 그대로예요';
const SAVED_1 = '버전 1로 저장했어요';

/** 이름 꼬리 숫자 뒤 조사(graph/rules.ts josa · 지적 12): (2) · (3) · (10) · (7). */
const JOSA: readonly { word: string; pair: string; expected: string }[] = [
  { word: '(2)', pair: '을/를', expected: '(2)를' },
  { word: '(3)', pair: '을/를', expected: '(3)을' },
  { word: '(10)', pair: '을/를', expected: '(10)을' },
  { word: '대형주 돌파 (2)', pair: '이/가', expected: '대형주 돌파 (2)가' },
  { word: '대형주 돌파 (3)', pair: '으로/로', expected: '대형주 돌파 (3)으로' },
  { word: '대형주 돌파 (7)', pair: '으로/로', expected: '대형주 돌파 (7)로' },
];

const VERSIONS = [1, 2, 3, 10] as const;

/** 조사가 붙는 마지막 글자(숫자 · 글자) · '(7)' 꼴은 괄호 안 숫자. */
function tail(word: string): string {
  return word.replace(/\)$/, '').trim().slice(-1);
}

describe('조사 견본(버전 1 · 2 · 3 · 10 · 얼린 기대값)', () => {
  it('(으)로: 1로 · 2로 · 3으로 · 10으로 — 지금 화면의 josaRo와 같다', () => {
    expect(VERSIONS.map((n) => `버전 ${String(n)}${josaRo(n)} 저장`)).toEqual(
      VERSIONS.map((n) => SAVE[n]),
    );
    expect(`버전 1${josaRo(1)} 저장했어요`).toBe(SAVED_1);
  });

  it('은/는 · 과/와: 받침 판정이 lib/format.endsWithConsonant와 같다', () => {
    for (const n of VERSIONS) {
      const word = `버전 ${String(n)}`;
      const closed = endsWithConsonant(word);
      expect(word + (closed ? '은' : '는')).toBe(EUN[n]);
      expect(word + (closed ? '과' : '와')).toBe(GWA[n]);
    }
  });

  it('이/가 · 을/를 · 떠나기 글: 받침 판정이 endsWithConsonant와 같다', () => {
    for (const { word, pair, expected } of WITH) {
      expect(word + (endsWithConsonant(word) ? pair[0] : pair[1])).toBe(expected);
    }
    expect(LEAVE_BODY).toContain(`버전 1${endsWithConsonant('버전 1') ? '은' : '는'}`);
  });

  it('이름 꼬리 숫자 (n) 뒤 조사: 괄호 안 숫자의 받침 · (으)로는 josaRo와 같다', () => {
    for (const { word, pair, expected } of JOSA) {
      const [a, b] = pair.split('/') as [string, string];
      const last = tail(word);
      const chosen = pair === '으로/로' ? josaRo(Number(last)) : endsWithConsonant(last) ? a : b;
      expect(word + chosen).toBe(expected);
    }
  });
});
