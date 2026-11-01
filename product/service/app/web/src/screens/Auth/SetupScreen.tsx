// MVP-01 비밀번호 만들기 (기본 · 두 비밀번호 다름) → MVP-02 복구 코드 (기본 · 적어 둠).
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { api, isApiError } from '../../api/client';
import { keys } from '../../api/mvp';
import { Box } from '../../components/Box';
import { Button } from '../../components/Buttons';
import { Card } from '../../components/Card';
import { Checkbox } from '../../components/Controls';
import { TextField } from '../../components/Field';
import { authCopy } from '../../copy/auth';
import { copy } from '../../copy';
import { Page } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';
import { RecoveryCode } from './RecoveryCode';
import styles from './Auth.module.css';

export function SetupScreen() {
  useDocumentTitle(copy.pages.setup);
  const t = authCopy.setup;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [adult, setAdult] = useState(false);
  const [terms, setTerms] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [code, setCode] = useState<string | null>(null);

  const mismatch = pw2.length > 0 && pw !== pw2;
  const ready = pw.length >= 8 && pw === pw2 && adult && terms && !busy;

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ recovery_code: string }>('/api/setup', {
        password: pw,
        password2: pw2,
        adult,
        terms,
      });
      setCode(r.recovery_code);
      setPw('');
      setPw2('');
    } catch (e) {
      setError(isApiError(e) ? e.message : copy.common.noConnection);
    } finally {
      setBusy(false);
    }
  };

  if (code) {
    const r = authCopy.recovery;
    return (
      <Page width="narrow">
        <div className={styles.head}>
          <p className="t-label c-accent">{r.eyebrow}</p>
          <h1 className="t-title">{r.title}</h1>
          <p className={`t-body ${styles.lead}`}>{r.lead}</p>
        </div>
        <RecoveryCode
          code={code}
          nextLabel={copy.common.next}
          onNext={() => {
            void qc
              .invalidateQueries({ queryKey: keys.state })
              .then(() => navigate('/', { replace: true }));
          }}
        />
      </Page>
    );
  }

  return (
    <Page width="narrow">
      <div className={styles.head}>
        <p className="t-label c-accent">{t.eyebrow}</p>
        <h1 className="t-title">{t.title}</h1>
        <p className={`t-body ${styles.lead}`}>{t.lead}</p>
      </div>
      <form
        className="stack-block"
        onSubmit={(e) => {
          e.preventDefault();
          if (ready) void submit();
        }}
      >
        <TextField
          label={t.password}
          type="password"
          autoComplete="new-password"
          value={pw}
          onChange={(e) => {
            setPw(e.target.value);
          }}
          hint={t.passwordHint}
        />
        <TextField
          label={t.password2}
          type="password"
          autoComplete="new-password"
          value={pw2}
          onChange={(e) => {
            setPw2(e.target.value);
          }}
          error={mismatch ? t.mismatch : undefined}
        />
        <Checkbox checked={adult} onChange={setAdult}>
          {t.adult}
        </Checkbox>
        <Card>
          <h2 className="t-heading-1">{t.termsTitle}</h2>
          <ul className={styles.terms}>
            {t.terms.map((line) => (
              <li key={line} className={`t-body ${styles.termItem}`}>
                {line}
              </li>
            ))}
          </ul>
          <Checkbox checked={terms} onChange={setTerms}>
            {t.agree}
          </Checkbox>
        </Card>
        {error ? <Box tone="error" title={error} strongTitle /> : null}
        <Button kind="primary" type="submit" className="full" disabled={!ready}>
          {t.next}
        </Button>
      </form>
    </Page>
  );
}
