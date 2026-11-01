// 복구 코드 카드 (처음 열기 MVP-02 · 비밀번호 다시 만들기 MVP-04 새 복구 코드).
import clsx from 'clsx';
import { useState } from 'react';
import { Button } from '../../components/Buttons';
import { Box } from '../../components/Box';
import { Card } from '../../components/Card';
import { Checkbox } from '../../components/Controls';
import { copy } from '../../copy';
import { authCopy } from '../../copy/auth';
import styles from './Auth.module.css';

export function RecoveryCode({
  code,
  nextLabel,
  onNext,
}: {
  code: string;
  nextLabel: string;
  onNext: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [wrote, setWrote] = useState(false);
  const t = authCopy.recovery;
  return (
    <>
      <Card>
        <p className="t-caption c-muted">{t.codeLabel}</p>
        <p className={clsx('t-title', styles.code)}>{code}</p>
        <Button
          kind="default"
          className="full"
          onClick={() => {
            void navigator.clipboard.writeText(code).then(() => {
              setCopied(true);
            });
          }}
        >
          {copied ? copy.common.copied : copy.common.copy}
        </Button>
        <Box tone="warn">{t.once}</Box>
      </Card>
      <Checkbox checked={wrote} onChange={setWrote}>
        {t.wrote}
      </Checkbox>
      <Button kind="primary" className="full" disabled={!wrote} onClick={onNext}>
        {nextLabel}
      </Button>
    </>
  );
}
