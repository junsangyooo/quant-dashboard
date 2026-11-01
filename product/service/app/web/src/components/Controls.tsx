// Figma: 체크 (선택 = 예 | 아니오).
import clsx from 'clsx';
import type { ChangeEvent, ReactNode } from 'react';
import { Check } from 'lucide-react';
import styles from './Controls.module.css';

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
