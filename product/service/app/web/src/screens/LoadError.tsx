// The one load-failure block every screen uses: message + 다시 불러오기.
import { Box } from '../components/Box';
import { Button } from '../components/Buttons';
import { copy } from '../copy';
import { Page } from '../shell/Layout';

export function LoadError({
  onRetry,
  message,
}: {
  onRetry: () => void;
  message?: string | undefined;
}) {
  return (
    <Page width="narrow">
      <Box tone="error" title={message ?? copy.common.loadFailed} strongTitle role="alert" />
      <Button kind="default" className="full" onClick={onRetry}>
        {copy.common.retry}
      </Button>
    </Page>
  );
}
