// SCR-PIN · 확인 중 (명세 loading, 그림 없음): 6칸 채운 채 잠금, 칸 아래 작은 스피너, 키패드 비활성.
import type { FixtureBundle } from '../types';
import { NOW } from '../ops';

const bundle = {
  id: 'pin.loading',
  now: NOW,
  responses: {
    'POST /api/auth/pin': { $pending: true },
  },
} satisfies FixtureBundle;

export default bundle;
