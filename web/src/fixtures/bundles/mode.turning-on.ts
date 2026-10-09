// SCR-MODE · 켜는 중 (Figma 1:64451): 체크 유지, PIN 칸 비움, '바꾸는 중' + '실계좌 잔고 확인 중 ·
// 다시 누를 수 없어요'. The turn-on request stays open.
import type { FixtureBundle } from '../types';
import { NOW, modePaper, shell } from '../ops';

const bundle = {
  id: 'mode.turning-on',
  now: NOW,
  responses: {
    '/api/shell': shell(),
    '/api/mode': modePaper(),
    'POST /api/mode/live': { $pending: true },
  },
} satisfies FixtureBundle;

export default bundle;
