// MVP-04 비밀번호 다시 만들기: 기본 · 새 복구 코드.
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { CircleCheck } from 'lucide-react';
import { api, isApiError } from '../../api/client';
import { Box } from '../../components/Box';
import { Button } from '../../components/Buttons';
import { TextField } from '../../components/Field';
import { copy } from '../../copy';
import { authCopy } from '../../copy/auth';
import { BackLink, Page } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';
import { RecoveryCode } from './RecoveryCode';
import styles from './Auth.module.css';

export function RecoverScreen() {
  useDocumentTitle(copy.pages.recover);
  const t = authCopy.recover;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [code, setCode] = useState('');
  const [pw, setPw] = useState('');
  const [pw2, setPw2] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newCode, setNewCode] = useState<string | null>(null);
  const mismatch = pw2.length > 0 && pw !== pw2;
  const ready =
    code.replace(/[^0-9A-Za-z]/g, '').length === 16 && pw.length >= 8 && pw === pw2 && !busy;

  if (newCode) {
    const r = authCopy.recovery;
    return (
      <Page width="narrow">
        <p className={`t-body-strong ${styles.done}`}>
          <CircleCheck size={20} className={styles.doneIcon} aria-hidden />
          {r.newDone}
        </p>
        <div className={styles.head}>
          <h1 className="t-title">{r.newTitle}</h1>
          <p className={`t-body ${styles.lead}`}>{r.newLead}</p>
        </div>
        <RecoveryCode
          code={newCode}
          nextLabel={r.toHome}
          onNext={() => {
            void qc.invalidateQueries().then(() => navigate('/', { replace: true }));
          }}
        />
      </Page>
    );
  }

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ recovery_code: string }>('/api/recover', {
        recovery_code: code,
        password: pw,
        password2: pw2,
      });
      setNewCode(r.recovery_code);
    } catch (e) {
      setError(isApiError(e) ? e.message : copy.common.noConnection);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page width="narrow">
      <BackLink to="/login">{t.back}</BackLink>
      <div className={styles.head}>
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
          label={t.code}
          value={code}
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => {
            setCode(e.target.value.toUpperCase());
          }}
          hint={t.codeHint}
        />
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
          error={mismatch ? authCopy.setup.mismatch : undefined}
        />
        <Box tone="info" icon="info">
          {t.note}
        </Box>
        {error ? <Box tone="error" title={error} strongTitle role="alert" /> : null}
        <Button kind="primary" type="submit" className="full" disabled={!ready}>
          {t.submit}
        </Button>
      </form>
    </Page>
  );
}
