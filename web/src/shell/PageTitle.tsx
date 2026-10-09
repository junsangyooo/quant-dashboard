// Sub-page title (작동 · 모의투자·실전 · 설정): ‹ back + type/title heading (Figma '페이지 제목').
import clsx from 'clsx';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { ChevronLeft, X } from 'lucide-react';
import { copy } from '../copy';
import styles from './AppShell.module.css';

export interface PageTitleProps {
  children: ReactNode;
  /** Where ‹ goes (sub-pages return to 자산). */
  backTo?: string | undefined;
  /** Sheet style: × instead of ‹ (그날 패널). */
  close?: boolean | undefined;
  className?: string | undefined;
}

export function PageTitle({ children, backTo = '/', close, className }: PageTitleProps) {
  const Icon = close ? X : ChevronLeft;
  return (
    <div className={clsx(styles.pageTitle, className)}>
      <Link to={backTo} className={styles.back} aria-label={close ? copy.close : copy.back}>
        <Icon size={24} aria-hidden />
      </Link>
      <h1 className="t-title">{children}</h1>
    </div>
  );
}
