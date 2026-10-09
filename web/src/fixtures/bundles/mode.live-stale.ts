// SCR-MODE · 실전 중 자료 낡음 (명세 error, 그림 없음): 공통 배너만 — 실전 중에는 점검 칸이 없어요.
import type { FixtureBundle } from '../types';
import { LIVE_ON_AT, NOW, modeLive, staleShell } from '../ops';

const bundle = {
  id: 'mode.live-stale',
  now: NOW,
  responses: {
    '/api/shell': staleShell({ mode: 'live', liveSince: LIVE_ON_AT }),
    '/api/mode': modeLive(),
  },
} satisfies FixtureBundle;

export default bundle;
