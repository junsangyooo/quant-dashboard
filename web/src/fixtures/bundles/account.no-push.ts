// SCR-ACCOUNT · 알림 불가 (Figma 1:65568) — 예시-값표 §3: iPhone Safari 탭(홈 화면 앱 아님).
// '이 기기는 알림을 못 받아요 · Safari 탭' + '공유 → 홈 화면에 추가 → 앱에서 다시 켜기'. 사건 스위치·시험
// 알림은 그대로(다른 기기용). The drawing keeps 'iPhone · 홈 화면 앱' in the device card; a Safari tab
// is named 'iPhone · Safari' by the server, so this bundle says so.
import type { AccountResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { NOW, account, shell } from '../ops';

const base = account();
const safariTab: AccountResponse = {
  thisDevice: { ...base.thisDevice, name: 'iPhone · Safari', kind: 'iphone-safari' },
  notifications: {
    ...base.notifications,
    thisDevice: { supported: false, reason: 'safari-tab', subscribed: false },
  },
};

const bundle = {
  id: 'account.no-push',
  now: NOW,
  responses: {
    '/api/shell': shell(),
    '/api/account': safariTab,
    'PUT /api/account/notifications': { savedAt: NOW },
    'POST /api/account/push/test': {
      results: [
        { device: 'iPhone', ok: true, at: NOW },
        { device: 'MacBook · Chrome', ok: true, at: NOW },
      ],
    },
  },
} satisfies FixtureBundle;

export default bundle;
