// SCR-ACCOUNT · 로드 중 (명세 loading, 그림 없음): the account request stays open.
import type { FixtureBundle } from '../types';
import { NOW, shell } from '../ops';

const bundle = {
  id: 'account.loading',
  now: NOW,
  responses: {
    '/api/shell': shell(),
    '/api/account': { $pending: true },
  },
} satisfies FixtureBundle;

export default bundle;
