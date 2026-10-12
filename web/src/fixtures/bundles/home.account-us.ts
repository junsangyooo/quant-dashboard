// SCR-HOME · 계좌별 보기 · 미국 $ (no drawing; the owner's plan of 2026-10-12): the 모의투자 world
// (값표 §1, 10/7 16:10) with the switch on 미국 계좌 — $3,526.56, ▼ −$149.95 · −4.08%, its own line
// and rows in dollars (S&P 500 ETF −5.4% in dollars; −6.0% in won with the rate). Same answers as
// home.paper.
import type { FixtureBundle } from '../types';
import homePaper from './home.paper';

const bundle = {
  ...homePaper,
  id: 'home.account-us',
  search: 'account=us',
} satisfies FixtureBundle;

export default bundle;
