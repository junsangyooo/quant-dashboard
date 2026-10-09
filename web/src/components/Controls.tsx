// Figma: 입력/PIN 칸 (빈 | 채움 | 포커스 | 오류 | 비활성), 키/숫자 (숫자 | 지우기 | 빈),
// 토글 (켜짐 = 예 | 아니오), 체크 (선택 = 예 | 아니오), 스위치/모드 (선택 = 모의투자 | 실전).
import clsx from 'clsx';
import { useRef, type ChangeEvent, type KeyboardEvent, type ReactNode } from 'react';
import { Check, CircleCheck, Delete } from 'lucide-react';
import { copy } from '../copy';
import type { Mode } from './Badges';
import styles from './Controls.module.css';

// ── 입력/PIN 칸 ──────────────────────────────────────────────────────────────
export type PinCellState = 'empty' | 'filled' | 'focus' | 'error' | 'disabled';

/** One drawn PIN slot. The real input is owned by the PIN screen. */
export function PinCell({
  state,
  className,
}: {
  state: PinCellState;
  className?: string | undefined;
}) {
  return (
    <span className={clsx(styles.pinCell, styles[`pin-${state}`], className)} aria-hidden>
      {state === 'filled' ? <span className={styles.pinDot} /> : null}
    </span>
  );
}

// ── 키/숫자 ──────────────────────────────────────────────────────────────────
export type KeypadKeyProps =
  | {
      kind: 'digit';
      digit: string;
      onPress?: (() => void) | undefined;
      disabled?: boolean | undefined;
    }
  | { kind: 'delete'; onPress?: (() => void) | undefined; disabled?: boolean | undefined }
  | { kind: 'blank' };

export function KeypadKey(props: KeypadKeyProps) {
  if (props.kind === 'blank') return <span className={styles.key} aria-hidden />;
  if (props.kind === 'delete') {
    return (
      <button
        type="button"
        className={clsx(styles.key, styles['key-delete'])}
        aria-label={copy.pin.delete}
        disabled={props.disabled}
        onClick={props.onPress}
      >
        <Delete size={24} aria-hidden />
      </button>
    );
  }
  return (
    <button
      type="button"
      className={clsx(styles.key, styles['key-digit'], 't-title')}
      disabled={props.disabled}
      onClick={props.onPress}
    >
      {props.digit}
    </button>
  );
}

// ── 토글 ─────────────────────────────────────────────────────────────────────
export interface ToggleProps {
  checked: boolean;
  onChange?: ((next: boolean) => void) | undefined;
  disabled?: boolean | undefined;
  /** Name it with a visible label (aria-labelledby) or aria-label. */
  'aria-label'?: string | undefined;
  'aria-labelledby'?: string | undefined;
  className?: string | undefined;
}

export function Toggle({ checked, onChange, disabled, className, ...aria }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange?.(!checked)}
      className={clsx(styles.toggle, className)}
      {...aria}
    >
      <span className={styles.knob} />
    </button>
  );
}

// ── 체크 ─────────────────────────────────────────────────────────────────────
export interface CheckboxProps {
  checked: boolean;
  onChange?: ((next: boolean) => void) | undefined;
  disabled?: boolean | undefined;
  /** Visible label next to the box. Without one, pass aria-label. */
  children?: ReactNode;
  'aria-label'?: string | undefined;
  className?: string | undefined;
}

export function Checkbox({
  checked,
  onChange,
  disabled,
  children,
  className,
  ...aria
}: CheckboxProps) {
  return (
    <label className={clsx(styles.checkLabel, className)}>
      <input
        type="checkbox"
        className={styles.checkInput}
        checked={checked}
        disabled={disabled}
        onChange={(e: ChangeEvent<HTMLInputElement>) => onChange?.(e.target.checked)}
        {...aria}
      />
      <span className={clsx(styles.checkBox, checked && styles.checkBoxOn)} aria-hidden>
        {checked ? <Check size={18} /> : null}
      </span>
      {children !== undefined ? <span className="t-body">{children}</span> : null}
    </label>
  );
}

// ── 스위치/모드 ──────────────────────────────────────────────────────────────
export interface ModeSwitchProps {
  value: Mode;
  onSelect?: ((mode: Mode) => void) | undefined;
  'aria-label'?: string | undefined;
  className?: string | undefined;
}

const MODES: readonly Mode[] = ['paper', 'live'];

/** Two-cell segmented control. Selecting 실전 is up to the screen (it scrolls, it does not switch). */
export function ModeSwitch({ value, onSelect, className, ...aria }: ModeSwitchProps) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>) => {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) return;
    e.preventDefault();
    const next: Mode = value === 'paper' ? 'live' : 'paper';
    refs.current[MODES.indexOf(next)]?.focus();
    onSelect?.(next);
  };
  return (
    <div role="radiogroup" className={clsx(styles.modeSwitch, className)} {...aria}>
      {MODES.map((mode, i) => {
        const selected = mode === value;
        return (
          <button
            key={mode}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            className={clsx(styles.modeCell, styles[`modeCell-${mode}`])}
            onClick={() => onSelect?.(mode)}
            onKeyDown={onKeyDown}
          >
            {selected ? <CircleCheck size={16} aria-hidden /> : null}
            <span className="t-body-strong">{copy.mode[mode]}</span>
          </button>
        );
      })}
    </div>
  );
}
