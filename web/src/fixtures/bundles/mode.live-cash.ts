// SCR-MODE · 실전 · 원화 · 달러 (D47·D48, 그림 없음), 10/7 16:10: 실전이 켜진 동안 14:20에 넣은
// 3,000,000원은 10/8 08:30부터 쓰고, 한국 61.4 : 미국 38.6이라 약 1,500,000원을 달러로 바꾸면 50:50.
// 정보 카드일 뿐 할 일이 아니고(헤더 '정상'), 막는 것도 없어요.
import type { FixtureBundle } from '../types';
import { LIVE_CASH, NOW, liveShell, modeLive } from '../ops';

const bundle = {
  id: 'mode.live-cash',
  now: NOW,
  responses: {
    '/api/shell': liveShell(),
    '/api/mode': modeLive({ liveCash: LIVE_CASH }),
  },
} satisfies FixtureBundle;

export default bundle;
