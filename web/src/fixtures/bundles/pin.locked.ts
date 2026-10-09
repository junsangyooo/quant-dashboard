// SCR-PIN · 잠김 (Figma 1:51378) — 예시-값표 §3 PIN 잠김: 이 접속 위치 연속 5회 실패 →
// '16:40까지 잠김 · 이 접속 위치' + '이미 열린 기기는 그대로 써요 · 실전 끄기도 그 기기에서 돼요'.
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { NOW } from '../ops';

const bundle = {
  id: 'pin.locked',
  now: NOW,
  responses: {
    'POST /api/auth/pin': {
      $status: 403,
      $body: { error: 'locked', until: kst('2026-10-07', '16:40'), scope: 'ip' },
    },
  },
} satisfies FixtureBundle;

export default bundle;
