// 설정 목록 행: 제목 · 한 줄 설명 · › (Figma MVP-05).
import clsx from 'clsx';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { ChevronRight } from 'lucide-react';
import styles from './MenuRow.module.css';

export function MenuRow({ to, title, line }: { to: string; title: ReactNode; line?: ReactNode }) {
  return (
    <Link to={to} className={styles.row}>
      <span className={styles.text}>
        <span className="t-body-strong">{title}</span>
        {line !== undefined ? <span className={clsx('t-caption', styles.line)}>{line}</span> : null}
      </span>
      <ChevronRight size={20} className={styles.chevron} aria-hidden />
    </Link>
  );
}
