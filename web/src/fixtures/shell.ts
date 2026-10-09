// Default world of 예시-값표 §0/§1 for the shell until the API client lands:
// 모의투자, header chip '정상 · 08:30 확인'.
import { copy } from '../copy';
import type { Mode } from '../components/Badges';
import type { HeaderStatus } from '../components/Chips';

export interface ShellState {
  mode: Mode;
  status: HeaderStatus;
  statusLabel: string;
}

export const shellFixture: ShellState = {
  mode: 'paper',
  status: 'ok',
  statusLabel: copy.headerStatus.ok('08:30'),
};
