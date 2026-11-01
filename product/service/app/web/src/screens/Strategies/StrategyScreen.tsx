// 12 전략 상세: 모의투자 전 · 모의투자 중 · 문제 있음 · 모의투자 끝내기 확인 (390 · 1440). 그래프 요약 카드.
import clsx from 'clsx';
import { useState, type ReactNode } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import { ChevronRight, Copy } from 'lucide-react';
import { api } from '../../api/client';
import {
  useCatalog,
  usePost,
  useStrategy,
  type Analysis,
  type StrategyDetail,
} from '../../api/mvp';
import { Box } from '../../components/Box';
import { Dots } from '../../components/Dots';
import { Button, LinkButton } from '../../components/Buttons';
import { Card, KeyValue } from '../../components/Card';
import { GraphView } from '../../components/graph/GraphView';
import { Sheet } from '../../components/Sheet';
import { StatusTag, VersionTag } from '../../components/Tags';
import { Toast, ToastSpacer } from '../../components/Toast';
import { copy } from '../../copy';
import { kindNames } from '../../copy/graph';
import { strategyCopy } from '../../copy/strategy';
import { KIND_ORDER, type RuleCatalog } from '../../graph/rules';
import { formatKrw, formatMonthDay } from '../../lib/format';
import { pct, tone, toneClass } from '../../lib/money';
import { runRange, startDayWeekday } from '../../lib/runDates';
import { useMediaQuery } from '../../lib/useMedia';
import { BackLink, Page, Split } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';
import { ruleCatalog } from '../Editor/model';
import { LoadError } from '../LoadError';
import { EndSheet, StartSheet } from './PaperSheets';
import paper from '../Paper/Paper.module.css';
import styles from './Strategies.module.css';

const d = strategyCopy.detail;

/** '빈칸 4 · ② 신호 2 · ③ 필터 1 · ④ 종목 선정 1 · 범위 밖 1'. */
export function problemWhere(a: Analysis, bySlot: { label: string; count: number }[]): string {
  const parts: string[] = [];
  for (const k of KIND_ORDER) {
    const n = a.counts[k] ?? 0;
    if (!n) continue;
    parts.push(d.part(kindNames[k], n));
    if (k === 'blank') for (const b of bySlot) parts.push(d.part(b.label, b.count));
  }
  return parts.join(' · ');
}

function PaperCard({
  s,
  onStart,
  onEnd,
}: {
  s: StrategyDetail;
  onStart: () => void;
  onEnd: () => void;
}) {
  if (s.paper) {
    const p = s.paper;
    const dir = tone(p.pnl);
    return (
      <Card>
        <h2 className="t-heading-1">{d.runningTitle(p.version_no)}</h2>
        <KeyValue label={d.start}>{startDayWeekday(p)}</KeyValue>
        <KeyValue label={d.cash0}>{formatKrw(p.cash0)}</KeyValue>
        <KeyValue label={d.now}>
          <span className={toneClass[dir]}>
            <Dots parts={[formatKrw(p.total), pct(p.pnl_pct)]} />
          </span>
        </KeyValue>
        <Button kind="dangerOutline" className="full" onClick={onEnd}>
          {d.end}
        </Button>
        <p className="t-caption c-muted">{d.endNote}</p>
      </Card>
    );
  }
  const v = s.version;
  const blocked = v.problems.length > 0;
  return (
    <Card>
      <h2 className="t-heading-1">{d.beforeTitle}</h2>
      <p className="t-caption c-muted">{d.beforeLine(v.no, v.problems.length)}</p>
      <Button kind="primary" className="full" disabled={blocked} onClick={onStart}>
        {d.startPaper}
      </Button>
    </Card>
  );
}

function PastRuns({ s }: { s: StrategyDetail }) {
  if (s.past_runs.length === 0) return null;
  return (
    <Card>
      <h2 className="t-heading-1">{d.pastTitle}</h2>
      {s.past_runs.map((r) => {
        const range = runRange(r);
        return (
          <Link key={r.id} to={`/history?run=${String(r.id)}`} className={styles.pastRow}>
            <span className="stack-tight">
              <span className="t-body-strong">{d.pastRow(r.version_no, range)}</span>
              <span className="t-caption c-muted">{d.pastLine(r.trades_count)}</span>
            </span>
            <span className={styles.pastRight}>
              <span className={clsx('t-body-strong', toneClass[tone(r.ret * 100, 2)])}>
                {pct(r.ret)}
              </span>
              <ChevronRight size={20} className="c-muted" aria-hidden />
            </span>
          </Link>
        );
      })}
    </Card>
  );
}

function Versions({ s }: { s: StrategyDetail }) {
  return (
    <Card>
      <h2 className="t-heading-1">{d.versions(s.versions.length)}</h2>
      {s.versions.map((v) => (
        <div key={v.id} className={styles.versionRow}>
          <span className="stack-tight">
            <span className="t-body-strong">{copy.common.version(v.no)}</span>
            <span className="t-caption c-muted">
              {d.versionLine(formatMonthDay(v.created_at), v.problems)}
            </span>
          </span>
          <VersionTag paper={v.paper} problems={v.problems} />
        </div>
      ))}
    </Card>
  );
}

function DeleteLine({ s, onDelete }: { s: StrategyDetail; onDelete: () => void }) {
  if (!s.deletable) return <p className="t-caption c-muted">{d.cannotDelete}</p>;
  return (
    <button type="button" className="t-label dangerLink" onClick={onDelete}>
      {d.delete}
    </button>
  );
}

export function GraphCard({
  cat,
  s,
  narrow,
}: {
  cat: RuleCatalog;
  s: StrategyDetail;
  narrow: boolean;
}) {
  const navigate = useNavigate();
  const to = `/strategies/${String(s.id)}/edit`;
  const a = s.analysis;
  return (
    <Card>
      <div className={styles.graphHead}>
        <h2 className="t-heading-1">{d.graphTitle(s.version.no, s.summary.nodes)}</h2>
        <LinkButton to={to}>{narrow ? d.bigView : d.openEditor}</LinkButton>
      </div>
      <p className="t-caption c-muted">
        {narrow
          ? d.graphLineNarrow(a.entry.length, a.sell.length)
          : d.graphLine(a.entry.length, a.sell.length)}
      </p>
      <button
        type="button"
        className={styles.graphButton}
        onClick={() => void navigate(to)}
        aria-label={narrow ? d.bigView : d.openEditor}
      >
        <GraphView cat={cat} graph={s.body.graph} analysis={a} label={s.name} />
      </button>
      <p className="t-caption c-muted">{d.readHow}</p>
    </Card>
  );
}

export function StrategyScreen() {
  const id = Number(useParams().id);
  const q = useStrategy(id);
  const catalog = useCatalog().data;
  const navigate = useNavigate();
  const narrow = !useMediaQuery('(min-width: 900px)');
  const [sheet, setSheet] = useState<'start' | 'end' | 'delete' | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const remove = usePost<undefined, unknown>(`/api/strategies/${String(id)}`, 'DELETE');
  useDocumentTitle(q.data?.name ?? copy.pages.strategy);
  if (q.isError) return <LoadError onRetry={() => void q.refetch()} />;
  const s = q.data;
  if (!s || !catalog) return null;
  const cat = ruleCatalog(catalog);
  const v = s.version;
  const blocked = v.problems.length > 0;
  const close = () => {
    setSheet(null);
  };

  const copyText = async () => {
    const r = await api.get<{ text: string }>(`/api/strategies/${String(id)}/copytext`);
    await navigator.clipboard.writeText(r.text);
    setToast(d.copied);
    window.setTimeout(() => {
      setToast(null);
    }, 4000);
  };

  const problemsBox = blocked ? (
    <Box tone="warn" title={d.problemsTitle(v.problems.length)}>
      <span>{d.problemsBody}</span>
      <span>{d.problemsWhere(problemWhere(s.analysis, v.blanks_by_slot))}</span>
    </Box>
  ) : null;

  const side = (extra: ReactNode) => (
    <>
      <PaperCard
        s={s}
        onStart={() => {
          setSheet('start');
        }}
        onEnd={() => {
          setSheet('end');
        }}
      />
      <PastRuns s={s} />
      {extra}
    </>
  );
  const tail = (
    <>
      <Versions s={s} />
      <DeleteLine
        s={s}
        onDelete={() => {
          setSheet('delete');
        }}
      />
    </>
  );

  return (
    <Page width="split">
      <Split
        main={
          <>
            <BackLink to="/strategies">{d.back}</BackLink>
            <h1 className="t-title">{s.name}</h1>
            <div className={styles.tags}>
              <VersionTag
                paper={s.paper !== null && s.paper.version_no === v.no}
                problems={v.problems.length}
              />
              <StatusTag kind="plain">{s.mode_name}</StatusTag>
            </div>
            <div className="buttons">
              <Button
                kind="default"
                onClick={() => void navigate(`/strategies/${String(id)}/edit`)}
              >
                {d.edit}
              </Button>
              <Button
                kind="default"
                disabled={blocked}
                onClick={() => void navigate(`/strategies/${String(id)}/backtest`)}
              >
                {d.backtest}
              </Button>
            </div>
            {problemsBox}
            <button
              type="button"
              className={clsx('t-label', styles.copyLink)}
              onClick={() => void copyText()}
            >
              <Copy size={16} aria-hidden />
              {d.copy}
            </button>
            <div className={paper.narrowOnly}>
              <div className="stack-block">{side(null)}</div>
            </div>
            <GraphCard cat={cat} s={s} narrow={narrow} />
            <div className={paper.narrowOnly}>
              <div className="stack-block">{tail}</div>
            </div>
          </>
        }
        side={
          <div className={clsx(paper.wideOnly, styles.sideTop)}>
            <div className="stack-block">{side(tail)}</div>
          </div>
        }
      />
      {sheet === 'start' ? (
        <StartSheet strategy={s.name} versionId={v.id} versionNo={v.no} onClose={close} />
      ) : null}
      {sheet === 'end' && s.paper ? (
        <EndSheet
          strategy={s.name}
          versionNo={s.paper.version_no}
          since={s.paper.started_at}
          lastEval={s.paper.last_d}
          held={s.paper.held}
          onClose={close}
        />
      ) : null}
      {sheet === 'delete' ? (
        <Sheet title={d.deleteTitle} onClose={close}>
          <p className="t-body">{d.deleteBody(s.name)}</p>
          <div className="buttons">
            <Button kind="default" onClick={close}>
              {copy.common.dismiss}
            </Button>
            <Button
              kind="danger"
              disabled={remove.isPending}
              onClick={() => {
                remove.mutate(undefined, {
                  onSuccess: () => {
                    void navigate('/strategies', { replace: true });
                  },
                });
              }}
            >
              {copy.common.delete}
            </Button>
          </div>
        </Sheet>
      ) : null}
      {toast ? <ToastSpacer /> : null}
      {toast ? <Toast>{toast}</Toast> : null}
    </Page>
  );
}
