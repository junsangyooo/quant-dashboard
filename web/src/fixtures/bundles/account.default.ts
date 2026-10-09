// SCR-ACCOUNT · 기본 (Figma 1:65384): 이 기기 iPhone · 홈 화면 앱 (들어온 시각 10/01 08:12), 알림 켜짐,
// 처음부터 6개 켜짐, 금액 숨기기 꺼짐, 10/07 15:38 저장됨, 시험 알림 iPhone · MacBook · Chrome 15:40 받음.
// Writes answer like the server would at 16:10.
import type { FixtureBundle } from '../types';
import { NOW, account, shell } from '../ops';

const bundle = {
  id: 'account.default',
  now: NOW,
  responses: {
    '/api/shell': shell(),
    '/api/account': account(),
    'PUT /api/account/notifications': { savedAt: NOW },
    'POST /api/account/push/test': {
      results: [
        { device: 'iPhone', ok: true, at: NOW },
        { device: 'MacBook · Chrome', ok: true, at: NOW },
      ],
    },
    'POST /api/account/pin': { $noContent: true },
    'POST /api/auth/logout': { $noContent: true },
    'POST /api/auth/logout-others': { $noContent: true },
  },
} satisfies FixtureBundle;

export default bundle;
