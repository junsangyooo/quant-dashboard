// SCR-MODE · 로드 중 (명세, 그림 없음): the mode request stays open → skeletons.
import type { FixtureBundle } from '../types';
import { NOW, shell } from '../ops';

const bundle = {
  id: 'mode.loading',
  now: NOW,
  responses: {
    '/api/shell': shell(),
    '/api/mode': { $pending: true },
  },
} satisfies FixtureBundle;

export default bundle;
