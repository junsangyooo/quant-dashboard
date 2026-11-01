// MVP-05 설정: 연결 · 비밀번호 변경 · 사용 조건 · 앱 정보 · 데이터 삭제 한 줄 · 잠그기.
import { useNavigate } from 'react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../../api/client';
import { useConnect } from '../../api/mvp';
import { Button } from '../../components/Buttons';
import { MenuRow } from '../../components/MenuRow';
import { copy } from '../../copy';
import { settingsCopy as t } from '../../copy/settings';
import { formatMonthDay } from '../../lib/format';
import { dayTime } from '../../lib/when';
import { Page } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';

export interface About {
  version: string;
  terms_at: string | null;
  created_at: string | null;
  address: string;
}

export const useAbout = () =>
  useQuery({ queryKey: ['about'], queryFn: () => api.get<About>('/api/about') });

export function SettingsScreen() {
  useDocumentTitle(copy.pages.settings);
  const conn = useConnect().data;
  const about = useAbout().data;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toss = conn?.toss;
  const check = toss?.last_check;
  const connectLine = !toss?.saved
    ? t.rows.connectNone
    : !check
      ? t.rows.connectSaved
      : check.ok
        ? t.rows.connectOk(dayTime(check.at))
        : t.rows.connectFail(check.title);

  return (
    <Page width="narrow" gutter="block">
      <h1 className="t-title">{t.title}</h1>
      <div>
        <MenuRow to="/settings/connect" title={t.rows.connect} line={connectLine} />
        <MenuRow to="/settings/password" title={t.rows.password} line={t.rows.passwordLine} />
        <MenuRow
          to="/settings/terms"
          title={t.rows.terms}
          line={about?.terms_at ? t.rows.termsLine(formatMonthDay(about.terms_at)) : undefined}
        />
        <MenuRow
          to="/settings/about"
          title={t.rows.about}
          line={about ? t.rows.aboutLine(about.version) : undefined}
        />
      </div>
      <p className="t-caption c-muted">{t.dataDelete}</p>
      <Button
        kind="default"
        className="full"
        onClick={() => {
          void api.post('/api/logout').then(async () => {
            qc.clear();
            await navigate('/login', { replace: true });
          });
        }}
      >
        {t.lock}
      </Button>
      <p className="t-caption c-muted">{t.lockLine}</p>
    </Page>
  );
}
