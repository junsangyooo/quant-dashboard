// A run of text in one Figma text style (type/*) and one semantic color.
import clsx from 'clsx';
import type { ReactNode } from 'react';
import styles from './Text.module.css';

export type TextStyle =
  | 'display'
  | 'title'
  | 'heading-1'
  | 'body'
  | 'body-strong'
  | 'figure'
  | 'label'
  | 'caption'
  | 'micro';

export type TextTone =
  | 'primary'
  | 'muted'
  | 'inverse'
  | 'accent'
  | 'gain'
  | 'loss'
  | 'flat'
  | 'success'
  | 'warning'
  | 'error'
  | 'ai';

export interface TextProps {
  variant: TextStyle;
  tone?: TextTone | undefined;
  /** Take the remaining width in a row. */
  grow?: boolean | undefined;
  align?: 'center' | 'end' | undefined;
  as?: 'span' | 'p' | 'h1' | 'h2' | 'h3' | 'strong' | undefined;
  id?: string | undefined;
  className?: string | undefined;
  children: ReactNode;
}

export function Text({
  variant,
  tone,
  grow,
  align,
  as: Tag = 'span',
  id,
  className,
  children,
}: TextProps) {
  return (
    <Tag
      id={id}
      className={clsx(
        `t-${variant}`,
        tone && styles[tone],
        grow && styles.grow,
        align && styles[`align-${align}`],
        className,
      )}
    >
      {children}
    </Tag>
  );
}
