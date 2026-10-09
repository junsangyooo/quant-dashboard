// SCR-PLAN · 출금 대기 (spec only; numbers as 자산 1:52342, 값표 §2.3): chip '출금 대기',
// weights without the waiting cash (49.3 · 50.7), first item '출금 대기 500,425원 · 10/12까지 ·
// 주문 0건', no banner.
import type { FixtureBundle } from '../types';
import homeWithdraw from './home.withdraw';

const bundle = {
  ...homeWithdraw,
  id: 'plan.withdraw',
} satisfies FixtureBundle;

export default bundle;
