// SCR-ACCOUNT · 1단계 (CONTRACT.md: 푸시 501, /api/account 의 thisDevice는 supported:false ·
// 'unsupported', devices []): a browser that can push reads this as '알림은 준비 중이에요'.
import type { AccountResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { NOW, events, shell } from '../ops';

const phase1: AccountResponse = {
  thisDevice: { name: 'Mac · Chrome', kind: 'mac', enteredAt: kst('2026-10-07', '16:02') },
  notifications: {
    thisDevice: { supported: false, reason: 'unsupported', subscribed: false },
    events: events(),
    hideAmounts: false,
    savedAt: null,
    devices: [],
    testResults: null,
  },
};

const notImplemented = {
  $status: 501,
  $body: { error: 'not-implemented', detail: { feature: 'push' } },
} as const;

const bundle = {
  id: 'account.push-not-ready',
  now: NOW,
  responses: {
    '/api/shell': shell(),
    '/api/account': phase1,
    'PUT /api/account/notifications': { savedAt: NOW },
    'POST /api/account/push': notImplemented,
    'POST /api/account/push/test': notImplemented,
  },
} satisfies FixtureBundle;

export default bundle;
