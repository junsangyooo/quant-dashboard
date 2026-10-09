// Placeholder for a tab page (자산 · 계획 · 기록 · 규칙) until its content is built.
// Tab pages have no visible title in Figma; the h1 is for assistive tech.
import { copy } from '../copy';
import { pageTitle, useDocumentTitle, type PageKey } from '../shell/page';

export function TabScreen({ page }: { page: PageKey }) {
  useDocumentTitle(pageTitle(page));
  return <h1 className="sr-only">{copy.pages[page]}</h1>;
}
