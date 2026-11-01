// 지적 2: '버전 n' 뒤 조사는 받침으로 고른다(버전 1 · 2 · 3 · 10).
import { describe, expect, it } from 'vitest';
import { editorCopy } from '../src/copy/editor';
import { version, withParticle } from '../src/copy/particles';

describe('조사', () => {
  it('(으)로: 받침 있으면 으로, 없거나 ㄹ이면 로', () => {
    expect([1, 2, 3, 10].map((n) => editorCopy.save(n))).toEqual([
      '버전 1로 저장',
      '버전 2로 저장',
      '버전 3으로 저장',
      '버전 10으로 저장',
    ]);
  });

  it('은/는 · 과/와 · 이/가 · 을/를', () => {
    expect([1, 2, 3, 10].map((n) => version(n, '은'))).toEqual([
      '버전 1은',
      '버전 2는',
      '버전 3은',
      '버전 10은',
    ]);
    expect([1, 2, 3, 10].map((n) => version(n, '과'))).toEqual([
      '버전 1과',
      '버전 2와',
      '버전 3과',
      '버전 10과',
    ]);
    expect(withParticle('버전 2', '이')).toBe('버전 2가');
    expect(withParticle('버전 3', '을')).toBe('버전 3을');
  });

  it('편집 글이 숫자에 맞는 조사를 쓴다', () => {
    expect(editorCopy.leave.body('조건 삭제 1', 1)).toBe(
      '저장하지 않은 변경이 사라져요 · 조건 삭제 1 · 버전 1은 그대로예요',
    );
    expect(editorCopy.save(2)).toBe('버전 2로 저장');
    expect(editorCopy.save(3)).toBe('버전 3으로 저장');
    expect(editorCopy.saved(1)).toBe('버전 1로 저장했어요');
  });
});

describe('이름 꼬리 숫자 뒤 조사(지적 12)', () => {
  it('(2) · (3) · (10)', async () => {
    const { josa } = await import('../src/graph/rules');
    expect(josa('(2)', '을/를')).toBe('(2)를');
    expect(josa('(3)', '을/를')).toBe('(3)을');
    expect(josa('(10)', '을/를')).toBe('(10)을');
    expect(josa('대형주 돌파 (2)', '이/가')).toBe('대형주 돌파 (2)가');
    expect(josa('대형주 돌파 (3)', '으로/로')).toBe('대형주 돌파 (3)으로');
    expect(josa('대형주 돌파 (7)', '으로/로')).toBe('대형주 돌파 (7)로');
  });
});
