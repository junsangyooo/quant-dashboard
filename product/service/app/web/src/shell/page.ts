import { useEffect } from 'react';
import { copy } from '../copy';
import type { TabKey } from '../components/Nav';

export type PageKey = keyof typeof copy.pages;

/** Route handle: which page, and how the shell frames it. */
export interface PageHandle {
  page: PageKey;
  /** tab: bottom tabs on 390; sub: no bottom tabs; auth: signed-out pages (no tabs, no gear). */
  kind: 'tab' | 'sub' | 'auth';
  tab?: TabKey | undefined;
}

export function isPageHandle(value: unknown): value is PageHandle {
  return typeof value === 'object' && value !== null && 'page' in value && 'kind' in value;
}

/** Sets document.title for the current page (WCAG 2.4.2). */
export function useDocumentTitle(title: string) {
  useEffect(() => {
    document.title = `${title} · ${copy.wordmark}`;
  }, [title]);
}
