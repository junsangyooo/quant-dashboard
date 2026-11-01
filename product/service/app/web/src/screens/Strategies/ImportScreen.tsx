// MVP-14 복사한 전략 붙여 넣기: 붙여 넣기 · 형식 아님 · 가져오기 확인.
import clsx from 'clsx';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { CircleX } from 'lucide-react';
import { api, isApiError } from '../../api/client';
import { useCatalog, usePost, type ImportPreview } from '../../api/mvp';
import { GraphView } from '../../components/graph/GraphView';
import { ruleCatalog } from '../Editor/model';
import { josa } from '../../graph/rules';
import { J } from '../../copy/particles';
import { Box } from '../../components/Box';
import { Button } from '../../components/Buttons';
import { Card, KeyValue } from '../../components/Card';
import { TextArea, TextField } from '../../components/Field';
import { copy } from '../../copy';
import { strategyCopy } from '../../copy/strategy';
import { BackLink, Page } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';
import styles from './Import.module.css';

const t = strategyCopy.import;

export function ImportScreen() {
  useDocumentTitle(copy.pages.import);
  const navigate = useNavigate();
  const [text, setText] = useState('');
  const [error, setError] = useState<{
    message: string;
    kind?: string | undefined;
    title?: string | undefined;
    detail?: string | undefined;
  } | null>(null);
  const catalog = useCatalog().data;
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [name, setName] = useState('');
  const accept = usePost<{ text: string; name: string }, { id: number }>('/api/import/accept');

  const check = async (value: string) => {
    setBusy(true);
    setError(null);
    try {
      const p = await api.post<ImportPreview>('/api/import/preview', { text: value });
      setPreview(p);
      setName(p.name);
    } catch (e) {
      if (isApiError(e)) {
        const b = e.body;
        setError({ message: e.message, kind: b?.kind, title: b?.title, detail: b?.detail });
      } else setError({ message: copy.common.noConnection });
    } finally {
      setBusy(false);
    }
  };

  if (preview) {
    return (
      <Page width="narrow">
        <BackLink to="/strategies">{t.back}</BackLink>
        <h1 className="t-title">{t.title}</h1>
        <Card>
          <p className="t-caption c-muted">{t.target}</p>
          <TextField
            label={t.name}
            value={name}
            maxLength={60}
            hint={
              preview.renamed
                ? t.renamedN(josa(/\(\d+\)$/.exec(preview.name)?.[0] ?? '(2)', J.eul))
                : undefined
            }
            onChange={(e) => {
              setName(e.target.value);
            }}
          />
          <KeyValue label={t.source} strong={false}>
            {preview.source_line}
          </KeyValue>
          <KeyValue label={t.mode} strong={false}>
            {preview.mode_name}
          </KeyValue>
        </Card>
        {preview.blanks > 0 ? (
          <Box tone="warn" icon="info" title={t.numbersTitle}>
            {t.numbersBody(preview.blanks)}
          </Box>
        ) : null}
        <Card>
          <h2 className="t-heading-1">{t.summary}</h2>
          <p className="t-caption c-muted">
            {t.summaryLine(
              preview.summary.nodes,
              preview.summary.entry,
              preview.summary.sell,
              preview.blanks,
            )}
          </p>
          {catalog ? (
            <GraphView
              cat={ruleCatalog(catalog)}
              graph={preview.body.graph}
              analysis={preview.analysis}
              label={t.summary}
            />
          ) : null}
          <p className="t-caption c-muted">{strategyCopy.detail.readHow}</p>
        </Card>
        {accept.error ? (
          <p className="t-caption c-error">
            {isApiError(accept.error) ? accept.error.message : copy.common.noConnection}
          </p>
        ) : null}
        <div className="buttons">
          <Button
            kind="default"
            onClick={() => {
              setPreview(null);
            }}
          >
            {copy.common.dismiss}
          </Button>
          <Button
            kind="primary"
            disabled={accept.isPending}
            onClick={() => {
              accept.mutate(
                { text, name: name.trim() },
                {
                  onSuccess: (r) => {
                    void navigate(`/strategies/${String(r.id)}`, { replace: true });
                  },
                },
              );
            }}
          >
            {t.accept}
          </Button>
        </div>
        <p className="t-caption c-muted">{t.acceptNote}</p>
      </Page>
    );
  }

  const notCopy = error !== null && error.kind !== 'graph' && error.message.startsWith(t.notCopy);
  const badGraph = error?.kind === 'graph';
  return (
    <Page width="narrow">
      <BackLink to="/strategies">{t.back}</BackLink>
      <h1 className="t-title">{t.title}</h1>
      <p className="t-body c-muted">{t.lead}</p>
      <TextArea
        tall
        aria-label={t.title}
        value={text}
        placeholder={t.placeholder}
        spellCheck={false}
        onChange={(e) => {
          setText(e.target.value);
          setError(null);
        }}
        error={
          error ? (
            <div className={styles.error}>
              <p className={clsx('t-body-strong', styles.errorTitle)}>
                <CircleX size={18} aria-hidden />
                {notCopy ? t.notCopy : badGraph ? error.title : error.message}
              </p>
              {notCopy ? <p className="t-caption">{t.notCopyBody}</p> : null}
              {badGraph ? <p className="t-caption">{t.badGraphBody(error.detail ?? '')}</p> : null}
            </div>
          ) : undefined
        }
      />
      <div className="buttons">
        <Button
          kind="default"
          onClick={() => {
            void navigator.clipboard.readText().then((clip) => {
              setText(clip);
              setError(null);
            });
          }}
        >
          {t.paste}
        </Button>
        <Button kind="primary" disabled={!text.trim() || busy} onClick={() => void check(text)}>
          {t.check}
        </Button>
      </div>
    </Page>
  );
}
