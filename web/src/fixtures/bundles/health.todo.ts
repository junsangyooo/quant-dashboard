// SCR-HEALTH · 할 일 1 (Figma 1:62685 / 1:63806) — 예시-값표 §0 · §1.5: 토스 연결 만료 12일 전,
// 그 밖은 정상. 헤더 '정상 · 08:30 확인', 배너 없음. The push row expands from /api/account.
import type { FixtureBundle } from '../types';
import { NOW, account, healthTodo, shell } from '../ops';

const bundle = {
  id: 'health.todo',
  now: NOW,
  responses: {
    '/api/shell': shell(),
    '/api/health': healthTodo(),
    '/api/account': account(),
  },
} satisfies FixtureBundle;

export default bundle;
