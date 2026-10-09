// Bottom sheet on 390, centred panel from 600px (기준 · 손대지 않았을 때 · 변동 분해 · 표식 범례 ·
// 사건 목록 — no Figma frame: 기획 §5 '그림 없음'). Native <dialog> + showModal(): the page
// behind is inert, focus stays inside, Escape and the backdrop close it, and focus returns to
// the opener.
import { useEffect, useId, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { copy } from '../../copy';
import { IconButton } from '../../components/Buttons';
import styles from './Sheet.module.css';

export interface SheetProps {
  title: ReactNode;
  onClose: () => void;
  children: ReactNode;
}

/** Mount it only while open; it opens itself. */
export function Sheet({ title, onClose, children }: SheetProps) {
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

  return (
    // The backdrop click lands on the <dialog> itself; keyboard users have Escape and ×.
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions
    <dialog
      ref={ref}
      className={styles.sheet}
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={styles.head}>
        <h2 id={titleId} className="t-heading-1">
          {title}
        </h2>
        <IconButton icon={X} label={copy.close} onClick={onClose} />
      </div>
      <div className={styles.body}>{children}</div>
    </dialog>
  );
}
