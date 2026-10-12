// 계좌 스위치 at the top of 자산 (the owner, 2026-10-12): 전체 · 한국 ₩ · 미국 $. A three-cell
// segmented control (the look of 스위치/모드); arrow keys move along it. No Figma frame yet.
import clsx from 'clsx';
import { useRef, type KeyboardEvent } from 'react';
import type { AccountId } from '../../api/types';
import { homeCopy } from '../../copy/home';
import styles from './Home.module.css';

export type HomeView = 'all' | AccountId;

export const HOME_VIEWS: readonly HomeView[] = ['all', 'kr', 'us'];

const ARROWS: Record<string, number> = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 };

export function AccountSwitch({
  value,
  onSelect,
}: {
  value: HomeView;
  onSelect: (view: HomeView) => void;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    const step = ARROWS[e.key];
    if (step === undefined) return;
    e.preventDefault();
    const i = (HOME_VIEWS.indexOf(value) + step + HOME_VIEWS.length) % HOME_VIEWS.length;
    const next = HOME_VIEWS[i] ?? 'all';
    refs.current[i]?.focus();
    onSelect(next);
  };
  return (
    <div role="radiogroup" aria-label={homeCopy.accounts.switchLabel} className={styles.switch}>
      {HOME_VIEWS.map((view, i) => {
        const selected = view === value;
        return (
          <button
            key={view}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            className={clsx(styles.switchCell, 't-label')}
            onClick={() => {
              onSelect(view);
            }}
            onKeyDown={onKeyDown}
          >
            {homeCopy.accounts.tabs[view]}
          </button>
        );
      })}
    </div>
  );
}
