// 설정 › 비밀번호 변경 (Figma 313:96023).
import { useState } from 'react';
import { api, isApiError } from '../../api/client';
import { Box } from '../../components/Box';
import { Button } from '../../components/Buttons';
import { TextField } from '../../components/Field';
import { copy } from '../../copy';
import { settingsCopy } from '../../copy/settings';
import { BackLink, Page } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';

export function PasswordScreen() {
  useDocumentTitle(copy.pages.password);
  const t = settingsCopy.password;
  const [current, setCurrent] = useState('');
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const mismatch = pw2.length > 0 && pw !== pw2;
  const ready = current.length > 0 && pw.length >= 8 && pw === pw2 && !busy;

  const submit = async () => {
    setBusy(true);
    setError(null);
    setDone(false);
    try {
      await api.post('/api/password', { current, password: pw, password2: pw2 });
      setDone(true);
      setCurrent('');
      setPw('');
      setPw2('');
    } catch (e) {
      setCurrent('');
      setError(isApiError(e) ? e.message : copy.common.noConnection);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page width="narrow" gutter="block">
      <BackLink to="/settings">{settingsCopy.back}</BackLink>
      <h1 className="t-title">{t.title}</h1>
      <form
        className="stack-block"
        onSubmit={(e) => {
          e.preventDefault();
          if (ready) void submit();
        }}
      >
        <TextField
          label={t.current}
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => {
            setCurrent(e.target.value);
          }}
          error={error ?? undefined}
        />
        <TextField
          label={t.next}
          type="password"
          autoComplete="new-password"
          value={pw}
          onChange={(e) => {
            setPw(e.target.value);
          }}
          hint={t.nextHint}
        />
        <TextField
          label={t.next2}
          type="password"
          autoComplete="new-password"
          value={pw2}
          onChange={(e) => {
            setPw2(e.target.value);
          }}
          error={mismatch ? t.mismatch : undefined}
        />
        {done ? <Box tone="success" title={t.done} role="status" /> : null}
        <Button kind="primary" type="submit" className="full" disabled={!ready}>
          {t.submit}
        </Button>
      </form>
    </Page>
  );
}
