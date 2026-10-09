// SCR-PLAN · 세션 없음 (spec only): 403 'session' → /pin?next=… and back after the PIN.
import type { FixtureBundle } from '../types';
import homePermission from './home.permission';

const bundle = {
  ...homePermission,
  id: 'plan.permission',
} satisfies FixtureBundle;

export default bundle;
