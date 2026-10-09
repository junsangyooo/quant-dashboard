// Six drawn PIN cells (입력/PIN 칸) over one real password input. The input takes keyboard
// digits and paste; the cells mirror it: a dot per digit, the next cell outlined
// ('다음 칸 보라 테두리'), red when the PIN was wrong, grey when the field is closed.
// Used by 입장 (SCR-PIN), 실전으로 켜기 (SCR-MODE) and PIN 바꾸기 (SCR-ACCOUNT).
import clsx from 'clsx';
import { useId, useState, type ChangeEvent, type Ref } from 'react';
import { PinCell, type PinCellState } from '../../components/Controls';
import styles from './PinField.module.css';

export const PIN_LENGTH = 6;

/** Digits only, at most six. */
export function pinDigits(raw: string): string {
  return raw.replace(/\D/g, '').slice(0, PIN_LENGTH);
}

export interface PinFieldProps {
  value: string;
  onChange: (value: string) => void;
  /** Called when the sixth digit arrives. */
  onComplete?: ((value: string) => void) | undefined;
  /**
   * normal · error (red cells) · busy (dots kept, closed while a request runs) ·
   * disabled (grey, empty).
   */
  state?: 'normal' | 'error' | 'busy' | 'disabled' | undefined;
  /** 'always': the next cell is outlined while entering (입장); 'focus': only while focused. */
  cursor?: 'always' | 'focus' | undefined;
  /** Accessible name; pass `labelledBy` instead when a visible label exists. */
  label?: string | undefined;
  labelledBy?: string | undefined;
  describedBy?: string | undefined;
  /** Focus the field when it appears (입장, an opened PIN form). */
  focusOnMount?: boolean | undefined;
  /** 'none' keeps the on-screen keyboard closed while the keypad is shown (390 입장). */
  inputMode?: 'numeric' | 'none' | undefined;
  autoComplete?: 'current-password' | 'new-password' | undefined;
  id?: string | undefined;
  inputRef?: Ref<HTMLInputElement> | undefined;
  className?: string | undefined;
}

export function PinField({
  value,
  onChange,
  onComplete,
  state = 'normal',
  cursor = 'focus',
  label,
  labelledBy,
  describedBy,
  focusOnMount,
  inputMode = 'numeric',
  autoComplete = 'current-password',
  id,
  inputRef,
  className,
}: PinFieldProps) {
  const fallbackId = useId();
  const [focused, setFocused] = useState(false);
  const closed = state === 'busy' || state === 'disabled';
  const complete = value.length >= PIN_LENGTH;
  const showCursor = !closed && !complete && (cursor === 'always' || focused);

  const cellState = (i: number): PinCellState => {
    if (state === 'disabled') return 'disabled';
    if (state === 'error') return 'error';
    if (i < value.length) return 'filled';
    if (i === value.length && showCursor) return 'focus';
    return 'empty';
  };

  const handleChange = (e: ChangeEvent<HTMLInputElement>) => {
    const next = pinDigits(e.target.value);
    onChange(next);
    if (next.length === PIN_LENGTH && value.length < PIN_LENGTH) onComplete?.(next);
  };

  return (
    <div className={clsx(styles.field, complete && styles.complete, className)}>
      <input
        ref={inputRef}
        id={id ?? fallbackId}
        className={styles.input}
        type="password"
        inputMode={inputMode}
        autoComplete={autoComplete}
        pattern="[0-9]*"
        maxLength={PIN_LENGTH}
        value={value}
        disabled={closed}
        // eslint-disable-next-line jsx-a11y/no-autofocus -- the PIN is the only thing on 입장
        autoFocus={focusOnMount}
        aria-label={labelledBy ? undefined : label}
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        aria-invalid={state === 'error' ? true : undefined}
        onChange={handleChange}
        onFocus={() => {
          setFocused(true);
        }}
        onBlur={() => {
          setFocused(false);
        }}
      />
      <span className={styles.cells} aria-hidden>
        {Array.from({ length: PIN_LENGTH }, (_, i) => (
          <PinCell key={i} state={cellState(i)} />
        ))}
      </span>
    </div>
  );
}
