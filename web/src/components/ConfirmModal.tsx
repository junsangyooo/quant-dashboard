// Figma: 모달/확인. Native <dialog> + showModal(): the page behind is inert, focus stays
// inside, Escape cancels, and focus returns to the opener when it closes.
import clsx from 'clsx';
import { useEffect, useId, useRef, type ReactNode } from 'react';
import { Button, type ButtonKind } from './Buttons';
import styles from './ConfirmModal.module.css';

export interface ConfirmModalProps {
  open: boolean;
  title: ReactNode;
  children?: ReactNode;
  cancelLabel: string;
  confirmLabel: string;
  confirmKind?: Exclude<ButtonKind, 'default'> | undefined;
  onCancel: () => void;
  onConfirm: () => void;
  /** `inline` draws the same box in the page flow (gallery, visual checks). */
  presentation?: 'modal' | 'inline' | undefined;
}

export function ConfirmModal({
  open,
  title,
  children,
  cancelLabel,
  confirmLabel,
  confirmKind = 'danger',
  onCancel,
  onConfirm,
  presentation = 'modal',
}: ConfirmModalProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const body = (
    <>
      <h2 id={titleId} className="t-heading-1">
        {title}
      </h2>
      {children !== undefined ? (
        <div className={clsx(styles.body, 't-body')}>{children}</div>
      ) : null}
      <div className={styles.buttons}>
        {/* Safe default: the non-destructive action takes the first focus. */}
        {/* eslint-disable-next-line jsx-a11y/no-autofocus */}
        <Button kind="default" block autoFocus={presentation === 'modal'} onClick={onCancel}>
          {cancelLabel}
        </Button>
        <Button kind={confirmKind} block onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </div>
    </>
  );

  if (presentation === 'inline') {
    return (
      <section className={clsx(styles.modal, styles.inline)} aria-labelledby={titleId}>
        {body}
      </section>
    );
  }

  return (
    <dialog
      ref={ref}
      className={styles.modal}
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
    >
      {body}
    </dialog>
  );
}
