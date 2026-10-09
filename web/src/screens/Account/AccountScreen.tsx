// SCR-ACCOUNT 설정 (Figma 1:65384 · 1:65568): ‹ 설정 → PIN 바꾸기 → 기기 → 알림. 1440 has no drawing:
// the same order in one 640 column (기획 §5 레이아웃 의도).
import { copy } from '../../copy';
import { accountCopy as t } from '../../copy/account';
import { useAccount } from '../../api/queries';
import { ErrorBlock, SkeletonBlock } from '../../components/State';
import { PageTitle } from '../../shell/PageTitle';
import { pageTitle, useDocumentTitle } from '../../shell/page';
import { DevicesCard } from './Devices';
import { NotificationsCard } from './Notifications';
import { PinChangeCard } from './PinChange';
import styles from './Account.module.css';

export function AccountScreen() {
  useDocumentTitle(pageTitle('account'));
  const q = useAccount();

  let body;
  if (q.isPending) {
    body = (
      <div className={styles.column} aria-busy="true">
        <SkeletonBlock height={84} />
        <SkeletonBlock height={297} />
        <SkeletonBlock height={600} />
      </div>
    );
  } else if (q.isError) {
    body = (
      <ErrorBlock message={t.error} onRetry={() => void q.refetch()} retrying={q.isFetching} />
    );
  } else {
    body = (
      <div className={styles.column}>
        <PinChangeCard />
        <DevicesCard device={q.data.thisDevice} />
        <NotificationsCard notifications={q.data.notifications} />
      </div>
    );
  }

  return (
    <div className={styles.screen}>
      <PageTitle>{copy.pages.account}</PageTitle>
      {body}
    </div>
  );
}
