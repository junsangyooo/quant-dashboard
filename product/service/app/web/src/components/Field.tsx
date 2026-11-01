// MVP/입력 칸: label above, 48px input (optional unit at the right), hint or error under it.
import clsx from 'clsx';
import {
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type TextareaHTMLAttributes,
} from 'react';
import styles from './Field.module.css';

interface FieldFrame {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  unit?: ReactNode;
  className?: string | undefined;
}

export type TextFieldProps = FieldFrame & Omit<InputHTMLAttributes<HTMLInputElement>, 'className'>;

export function TextField({ label, hint, error, unit, className, id, ...input }: TextFieldProps) {
  const auto = useId();
  const fid = id ?? auto;
  const hid = `${fid}-hint`;
  return (
    <div className={clsx(styles.field, className)}>
      {label !== undefined ? (
        <label htmlFor={fid} className={clsx('t-label', styles.label)}>
          {label}
        </label>
      ) : null}
      <div
        className={clsx(
          styles.box,
          error !== undefined && error !== null && styles.invalid,
          input.disabled && styles.disabled,
        )}
      >
        <input
          id={fid}
          className={clsx('t-body', styles.input)}
          aria-invalid={error !== undefined && error !== null ? true : undefined}
          aria-describedby={hint !== undefined || error ? hid : undefined}
          {...input}
        />
        {unit !== undefined ? <span className={clsx('t-body', styles.unit)}>{unit}</span> : null}
      </div>
      {error ? (
        <p id={hid} className={clsx('t-caption', styles.error)}>
          {error}
        </p>
      ) : hint !== undefined ? (
        <p id={hid} className={clsx('t-caption', styles.hint)}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export type TextAreaProps = FieldFrame &
  Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'className'> & { tall?: boolean | undefined };

export function TextArea({ label, hint, error, className, id, tall, ...area }: TextAreaProps) {
  const auto = useId();
  const fid = id ?? auto;
  const hid = `${fid}-hint`;
  return (
    <div className={clsx(styles.field, className)}>
      {label !== undefined ? (
        <label htmlFor={fid} className={clsx('t-label', styles.label)}>
          {label}
        </label>
      ) : null}
      <textarea
        id={fid}
        className={clsx('t-body', styles.area, tall && styles.tall, error && styles.invalid)}
        aria-invalid={error ? true : undefined}
        aria-describedby={hint !== undefined || error ? hid : undefined}
        {...area}
      />
      {error ? (
        <div id={hid} className={styles.errorSlot}>
          {error}
        </div>
      ) : hint !== undefined ? (
        <p id={hid} className={clsx('t-caption', styles.hint)}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}
