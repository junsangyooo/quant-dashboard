// Toast: one dark line near the bottom with an optional action (조건 삭제 → 되돌리기).
import clsx from 'clsx';
import type { ReactNode } from 'react';
import styles from './Toast.module.css';

export function Toast({
  children,
  action,
  onAction,
}: {
  children: ReactNode;
  action?: ReactNode;
  onAction?: (() => void) | undefined;
}) {
  return (
    <div className={styles.toast} role="status">
      <span className={clsx('t-body', styles.text)}>{children}</span>
      {action !== undefined ? (
        <button type="button" className={clsx('t-label', styles.action)} onClick={onAction}>
          {action}
        </button>
      ) : null}
    </div>
  );
}

/** Put it at the end of the page while a toast shows: the last button stays above the toast. */
export function ToastSpacer() {
  return <div className={styles.spacer} aria-hidden />;
}
