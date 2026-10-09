// Placeholder for a sub-page (작동 · 모의투자·실전 · 설정): ‹ title, no bottom tabs.
import { copy } from '../copy';
import { PageTitle } from '../shell/PageTitle';
import { pageTitle, useDocumentTitle, type PageKey } from '../shell/page';

export function SubScreen({ page }: { page: PageKey }) {
  useDocumentTitle(pageTitle(page));
  return <PageTitle>{copy.pages[page]}</PageTitle>;
}
