// Bottom sheet on 390 (grab bar, title, ×), centred panel from 900px (MVP rule: 1440 shows the same
// one column, at most 560 wide, centred). Native <dialog> + showModal(): the page behind is inert,
// focus stays inside, Escape and the backdrop close it, and focus returns to the opener.
import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { copy } from '../copy';
import { IconButton } from './Buttons';
import styles from './Sheet.module.css';

export interface SheetProps {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
  /** Title icon (조건 고르기: the stage icon). */
  icon?: ReactNode;
}

/** Mount it only while open; it opens itself. */
export function Sheet({ title, onClose, children, icon }: SheetProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (dialog && !dialog.open) dialog.showModal();
    return () => {
      if (dialog?.open) dialog.close();
      opener?.focus({ preventScroll: true });
    };
  }, []);

  const onKeyDown = (e: KeyboardEvent<HTMLDialogElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  };

  return (
    // The backdrop click lands on the <dialog> itself; keyboard users have Escape and ×.
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <dialog
      ref={ref}
      className={styles.sheet}
      aria-labelledby={titleId}
      onKeyDown={onKeyDown}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <span className={styles.grab} aria-hidden />
      <div className={styles.head}>
        <h2 id={titleId} className={`t-heading-1 ${styles.title}`}>
          {icon}
          {title}
        </h2>
        <IconButton icon={X} label={copy.close} onClick={onClose} />
      </div>
      <div className={styles.body}>{children}</div>
    </dialog>
  );
}
