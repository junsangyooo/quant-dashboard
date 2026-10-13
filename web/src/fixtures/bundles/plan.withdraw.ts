// SCR-PLAN · 실전 출금 대기 (값표 §2.3, PHASE3.md 2.5): the wait holds the sale's money only, so
// the chip is 목표 범위 안 and the next check goes on; weights without the waiting cash (49.6 ·
// 50.4), basis line '출금 대기 현금 제외', no '주문 0건' item, no banner.
import type { FixtureBundle } from '../types';
import homeWithdraw from './home.withdraw';

const bundle = {
  ...homeWithdraw,
  id: 'plan.withdraw',
} satisfies FixtureBundle;

export default bundle;
