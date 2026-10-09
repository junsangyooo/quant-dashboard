// SCR-PLAN · 로드 (spec only): card frames and gauge outlines stay, numbers, needles and
// timeline text are skeletons — the plan answer never arrives.
import type { FixtureBundle } from '../types';
import homeLoading from './home.loading';

const bundle = {
  ...homeLoading,
  id: 'plan.loading',
} satisfies FixtureBundle;

export default bundle;
