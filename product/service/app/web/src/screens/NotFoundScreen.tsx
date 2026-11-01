import { LinkButton } from '../components/Buttons';
import { copy } from '../copy';
import { Page } from '../shell/Layout';
import { useDocumentTitle } from '../shell/page';

export function NotFoundScreen() {
  useDocumentTitle(copy.pages.notFound);
  return (
    <Page width="narrow">
      <h1 className="t-title">{copy.pages.notFound}</h1>
      <p className="t-body c-muted">{copy.common.notFoundBody}</p>
      <LinkButton to="/">{copy.common.toHome}</LinkButton>
    </Page>
  );
}
