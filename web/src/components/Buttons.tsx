// Figma: 버튼 (종류 = 기본 | 주요 | 위험, 상태 = 보통 | 비활성), 버튼/아이콘, 버튼/링크,
// 버튼/펼침, 버튼/접기.
import clsx from 'clsx';
import type { ButtonHTMLAttributes, MouseEventHandler, ReactNode } from 'react';
import { Link } from 'react-router';
import { ChevronDown, ChevronRight, ChevronUp, type LucideIcon } from 'lucide-react';
import { copy } from '../copy';
import styles from './Buttons.module.css';

export type ButtonKind = 'default' | 'primary' | 'danger';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** 종류: 기본 | 주요 | 위험. 상태 = 비활성 is the native `disabled`. */
  kind?: ButtonKind | undefined;
  /** Stretch to share a row (모달/확인 button row). */
  block?: boolean | undefined;
}

export function Button({
  kind = 'default',
  block,
  className,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={clsx(
        styles.button,
        styles[kind],
        block && styles.block,
        't-body-strong',
        className,
      )}
      {...rest}
    />
  );
}

export interface IconButtonProps {
  icon: LucideIcon;
  /** Accessible name — the button shows only an icon. */
  label: string;
  to?: string | undefined;
  onClick?: MouseEventHandler<HTMLButtonElement> | undefined;
  iconSize?: number | undefined;
  className?: string | undefined;
}

export function IconButton({
  icon: Icon,
  label,
  to,
  onClick,
  iconSize = 20,
  className,
}: IconButtonProps) {
  const cls = clsx(styles.iconButton, className);
  const glyph = <Icon size={iconSize} aria-hidden />;
  return to ? (
    <Link to={to} className={cls} aria-label={label}>
      {glyph}
    </Link>
  ) : (
    <button type="button" className={cls} aria-label={label} onClick={onClick}>
      {glyph}
    </button>
  );
}

export interface LinkButtonProps {
  children: ReactNode;
  to?: string | undefined;
  onClick?: MouseEventHandler<HTMLButtonElement> | undefined;
  className?: string | undefined;
}

/** 버튼/링크: accent label + chevron-right. Navigates with `to`, otherwise acts in place. */
export function LinkButton({ children, to, onClick, className }: LinkButtonProps) {
  const cls = clsx(styles.link, className);
  const body = (
    <>
      <span className={clsx('t-label', styles.linkLabel)}>{children}</span>
      <ChevronRight size={16} aria-hidden />
    </>
  );
  return to ? (
    <Link to={to} className={cls}>
      {body}
    </Link>
  ) : (
    <button type="button" className={cls} onClick={onClick}>
      {body}
    </button>
  );
}

export interface DisclosureButtonProps {
  children?: ReactNode;
  onClick?: MouseEventHandler<HTMLButtonElement> | undefined;
  /** id of the region this button shows or hides. */
  controls?: string | undefined;
  className?: string | undefined;
}

/** 버튼/펼침: label + chevron-down, for collapsed content. */
export function ExpandButton({ children, onClick, controls, className }: DisclosureButtonProps) {
  return (
    <button
      type="button"
      aria-expanded={false}
      aria-controls={controls}
      onClick={onClick}
      className={clsx(styles.link, className)}
    >
      <span className={clsx('t-label', styles.linkLabel)}>{children}</span>
      <ChevronDown size={16} aria-hidden />
    </button>
  );
}

/** 버튼/접기: '접기' + chevron-up, for expanded content. */
export function CollapseButton({ children, onClick, controls, className }: DisclosureButtonProps) {
  return (
    <button
      type="button"
      aria-expanded
      aria-controls={controls}
      onClick={onClick}
      className={clsx(styles.link, className)}
    >
      <span className={clsx('t-label', styles.linkLabel)}>{children ?? copy.collapse}</span>
      <ChevronUp size={16} aria-hidden />
    </button>
  );
}
