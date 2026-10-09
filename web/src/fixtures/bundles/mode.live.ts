// SCR-MODE · 실전 (Figma 1:64317) — 예시-값표 §2.2: 실전 9/1부터 · 27일째, 두 장부 +1.13% ·
// +1.28% · +1.75%, 차이 분해 −0.02 −0.06 −0.07 = −0.15%p. The off modal reads /api/mode
// offPreview (the pending buy and the cash that stays). Turning off stays open here ('바꾸는 중').
import type { FixtureBundle } from '../types';
import { NOW, liveShell, modeLive } from '../ops';

const bundle = {
  id: 'mode.live',
  now: NOW,
  responses: {
    '/api/shell': liveShell(),
    '/api/mode': modeLive(),
    'POST /api/mode/paper': { $pending: true },
  },
} satisfies FixtureBundle;

export default bundle;
