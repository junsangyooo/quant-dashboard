// 설정 › 사용 조건 · 앱 정보 — no Figma frame; built from the 처음 열기 terms card and the
// 설정 rows (layout rule: one column, at most 560 wide).
import { Card, KeyValue } from '../../components/Card';
import { copy } from '../../copy';
import { settingsCopy } from '../../copy/settings';
import { termsCopy } from '../../copy/terms';
import { StatusTag } from '../../components/Tags';
import { formatMonthDayWeekday } from '../../lib/format';
import { BackLink, Page } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';
import { useAbout } from './SettingsScreen';
import styles from '../Auth/Auth.module.css';

export function TermsScreen() {
  useDocumentTitle(copy.pages.terms);
  const about = useAbout().data;
  return (
    <Page width="narrow" gutter="block">
      <BackLink to="/settings">{settingsCopy.back}</BackLink>
      <h1 className="t-title">{settingsCopy.rows.terms}</h1>
      <Card>
        <p className="stack-inline">
          <StatusTag kind="plain" className={styles.draftTag}>
            {termsCopy.draft}
          </StatusTag>
          <span className="t-caption c-muted">{termsCopy.draftLine}</span>
        </p>
        {termsCopy.sections.map((sec) => (
          <section key={sec.title} className="stack-tight">
            <h2 className="t-body-strong">{sec.title}</h2>
            <ul className={styles.terms}>
              {sec.lines.map((line) => (
                <li key={line} className={`t-body ${styles.termItem}`}>
                  {line}
                </li>
              ))}
            </ul>
          </section>
        ))}
        {about?.terms_at ? (
          <p className="t-caption c-muted">
            {settingsCopy.terms.agreedAt(formatMonthDayWeekday(about.terms_at))}
          </p>
        ) : null}
      </Card>
    </Page>
  );
}

export function AboutScreen() {
  useDocumentTitle(copy.pages.about);
  const about = useAbout().data;
  const t = settingsCopy.about;
  return (
    <Page width="narrow" gutter="block">
      <BackLink to="/settings">{settingsCopy.back}</BackLink>
      <h1 className="t-title">{settingsCopy.rows.about}</h1>
      <Card>
        <KeyValue label={t.version}>{about?.version ?? ''}</KeyValue>
        <KeyValue label={t.address}>{about?.address ?? ''}</KeyValue>
        <KeyValue label={t.data}>{t.dataPath}</KeyValue>
        <p className="t-caption c-muted">{t.ordersLine}</p>
      </Card>
      <p className="t-caption c-muted">{settingsCopy.dataDelete}</p>
    </Page>
  );
}
