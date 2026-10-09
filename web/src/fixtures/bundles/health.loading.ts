// SCR-HEALTH · 로드 중 (명세 loading, 그림 없음): the status request stays open. The summary
// keeps its frame as a skeleton and never pre-draws '정상'.
import type { FixtureBundle } from '../types';
import { NOW, shell } from '../ops';

const bundle = {
  id: 'health.loading',
  now: NOW,
  responses: {
    '/api/shell': shell(),
    '/api/health': { $pending: true },
  },
} satisfies FixtureBundle;

export default bundle;
