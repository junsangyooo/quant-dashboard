// 실전 화면(그림 V2-10 자산 · V2-11 계획 · V2-12 기록 · V2-13 할 일 · 알림 · V2-14 할 일 상세 · V2-30 실전 운용 시작 ·
// V2-32 멈추기). 숫자는 모두 /api/live/screen(실전)에서 와요 · 모의 숫자 0(R-V5).
import clsx from 'clsx';
import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { isApiError } from '../../api/client';
import {
  liveApi,
  useLive,
  useLivePreview,
  useLiveRefresh,
  type LiveScreen,
  type LiveTodo,
} from '../../api/live';
import { download } from '../../api/settingsV2';
import { LineChart } from '../../charts/LineChart';
import { LINE_HOME_1440 } from '../../charts/geometry/lineChart';
import { edgeAxis } from '../../charts/geometry/mvpAxis';
import { Box } from '../../components/Box';
import { Button } from '../../components/Buttons';
import { Checkbox } from '../../components/Controls';
import { TextField } from '../../components/Field';
import { Sheet } from '../../components/Sheet';
import { copy } from '../../copy';
import { liveCopy as t } from '../../copy/live';
import { formatKrw, formatKrwSigned, formatMonthDayWeekday } from '../../lib/format';
import { useDocumentTitle } from '../../shell/page';
import { Note, Panel, Status, TextLink, WizardPage, wizardStyles as w } from '../Setup/Wizard';
import styles from './Live.module.css';

const md = (d: string) => `${String(Number(d.slice(5, 7)))}/${String(Number(d.slice(8, 10)))}`;
const signClass = (v: number) => (v > 0 ? styles.gain : v < 0 ? styles.loss : undefined);
const errorText = (e: unknown) => (isApiError(e) ? e.message : copy.common.noConnection);

function StateChip({ s }: { s: LiveScreen }) {
  const label = s.halted ? t.halted : s.paused ? t.paused : s.running ? t.running : t.ended;
  return (
    <span className={clsx(styles.chip, s.halted ? styles.chipBad : styles.chipOk, 't-caption')}>
      ● {label}
    </span>
  );
}

function NotRunning({ s }: { s: LiveScreen }) {
  const navigate = useNavigate();
  return (
    <Panel title={t.home.notRunningTitle}>
      <ol className={clsx(styles.steps, 't-body')}>
        {t.home.steps.map((x) => (
          <li key={x}>{x}</li>
        ))}
      </ol>
      {s.paused ? <Status kind="wait">{t.paused}</Status> : null}
      <Button kind="primary" onClick={() => void navigate('/strategies')}>
        {t.home.toStrategies}
      </Button>
    </Panel>
  );
}

// ── V2-10 자산 ────────────────────────────────────────────────────────────────

export function LiveHomeScreen() {
  useDocumentTitle(copy.pages.home);
  const q = useLive();
  const s = q.data;
  const navigate = useNavigate();
  const [stop, setStop] = useState(false);
  if (!s) return null;
  const acc = s.account;
  const top = (
    <Panel>
      <h1 className="sr-only">{copy.pages.home}</h1>
      {acc ? (
        <>
          <span className="t-caption c-muted">
            {t.home.accountTotal(formatMonthDayWeekday(new Date()))}
          </span>
          <strong className={styles.big}>{formatKrw(acc.total)}</strong>
        </>
      ) : (
        <Status kind="wait">{t.home.noAccount}</Status>
      )}
    </Panel>
  );
  if (!s.running)
    return (
      <div className={w.page}>
        {top}
        <NotRunning s={s} />
      </div>
    );
  const equity = s.equity ?? 0;
  const amount = s.amount ?? 0;
  const pts = (s.curve ?? []).map(([date, value]) => ({ date, value }));
  const start = pts[0]?.date ?? (s.started_at ?? '').slice(0, 10);
  const end = pts.at(-1)?.date ?? start;
  const holdings = s.holdings ?? [];
  const manual = (s.account?.holdings ?? []).filter((h) => s.manual?.includes(h.sym));
  const buys = (s.plan_rows ?? []).filter((p) => p.side === 'buy');
  return (
    <div className={w.page}>
      {top}
      <section className={styles.runCard}>
        <div className={w.cardHead}>
          <span className={styles.chips}>
            <span className={clsx(styles.chipDark, 't-caption')}>{t.liveChip}</span>
            <StateChip s={s} />
            <span className="t-label c-accent">
              {s.strategy?.name} · {t.version(s.strategy?.version_no ?? 0)}
            </span>
          </span>
          <span className={w.buttons}>
            <Button onClick={() => void navigate('/plan')}>{t.home.settings}</Button>
            <Button
              kind="dangerOutline"
              onClick={() => {
                setStop(true);
              }}
            >
              {t.home.stop}
            </Button>
          </span>
        </div>
        <div className={w.cols}>
          <div className={w.main}>
            <span className="t-caption c-muted">
              {t.home.managed(md((s.started_at ?? '').slice(0, 10)), formatKrw(amount))}
            </span>
            <strong className={styles.big}>{formatKrw(equity)}</strong>
            <span className={clsx('t-body-strong', signClass(equity - amount))}>
              {formatKrwSigned(equity - amount)}
            </span>
            <div className={styles.grid2}>
              <Kv k={t.home.evalAmount} v={formatKrw(s.eval ?? 0)} />
              <Kv k={t.home.runCash} v={formatKrw(s.cash ?? 0)} />
              <Kv k={t.home.evalPnl} v={formatKrwSigned(holdings.reduce((a, h) => a + h.pnl, 0))} />
            </div>
            {s.next ? <Note>{t.home.schedule(formatMonthDayWeekday(s.next.for_d))}</Note> : null}
            <Box tone="warn" icon="warn">
              {t.home.watchNote}
            </Box>
          </div>
          <div className={w.side}>
            <strong className="t-label">{t.home.chart}</strong>
            {pts.length ? (
              <LineChart
                layout={LINE_HOME_1440}
                start={start}
                end={end === start ? start : end}
                axis={edgeAxis([...pts.map((p) => p.value), amount])}
                mine={{ key: 'mine', points: pts }}
                baseline={{
                  key: 'base',
                  points: pts.map((p) => ({ date: p.date, value: amount })),
                }}
                formatDate={md}
                label={t.home.chart}
              />
            ) : (
              <p className="t-caption c-muted">{t.home.none}</p>
            )}
          </div>
        </div>
      </section>
      <div className={w.cols}>
        <div className={w.main}>
          <Panel
            title={t.home.nextPlan(s.next ? formatMonthDayWeekday(s.next.for_d) : '—')}
            action={<TextLink onClick={() => void navigate('/plan')}>{t.home.seePlan}</TextLink>}
          >
            <span className="t-body-strong">
              {t.home.planLine(
                buys.length,
                formatKrw(buys.reduce((a, p) => a + (p.max ?? 0), 0)),
                (s.plan_rows ?? []).length - buys.length,
              )}
            </span>
            {(s.plan_rows ?? []).map((p) => (
              <div key={p.sym + p.side} className={w.kv}>
                <span className="t-body">
                  <SideTag side={p.side} /> {p.name} {p.qty}
                  {t.shares}
                </span>
                {p.max ? <span className="t-body">{formatKrw(p.max)}</span> : null}
              </div>
            ))}
          </Panel>
          <Panel title={t.home.holdings}>
            <p className="t-caption c-muted">
              {t.home.strategyHold(s.strategy?.name ?? '', holdings.length)}
            </p>
            {holdings.map((h) => (
              <div key={h.sym} className={styles.row}>
                <span>
                  <strong className="t-body-strong">{h.name}</strong>
                  <br />
                  <span className="t-caption c-muted">
                    {h.sym} · {h.qty}
                    {t.shares} · {formatKrw(h.avg)}
                  </span>
                </span>
                <span className="t-body">{formatKrw(h.price)}</span>
                <span className="t-body-strong">{formatKrw(h.value)}</span>
                <span className={clsx('t-body', signClass(h.pnl))}>{formatKrwSigned(h.pnl)}</span>
              </div>
            ))}
            {manual.length ? (
              <p className="t-caption c-muted">{t.home.manualHold(manual.length)}</p>
            ) : null}
            {manual.map((h) => (
              <div key={h.sym} className={styles.row}>
                <span>
                  <strong className="t-body-strong">{h.name}</strong>
                  <br />
                  <span className="t-caption c-muted">
                    {h.sym} · {h.qty}
                    {t.shares}
                  </span>
                </span>
                <span className="t-body">{formatKrw(h.price)}</span>
                <span className="t-body-strong">{formatKrw(h.qty * h.price)}</span>
                <span />
              </div>
            ))}
          </Panel>
        </div>
        <div className={w.side}>
          <Panel
            title={t.home.recent}
            action={<TextLink onClick={() => void navigate('/history')}>{t.home.record}</TextLink>}
          >
            {(s.recent ?? []).length === 0 ? (
              <p className="t-caption c-muted">{t.home.none}</p>
            ) : null}
            {(s.recent ?? []).map((f, i) => (
              <div key={`${f.d}${f.sym}${String(i)}`} className={w.kv}>
                <span className="t-caption c-muted">{md(f.d)}</span>
                <span className="t-body">
                  {f.name} <SideTag side={f.side === 'buy' ? 'buy' : 'sell'} />
                </span>
                <strong className="t-body">{formatKrw(f.qty * f.price)}</strong>
              </div>
            ))}
          </Panel>
        </div>
      </div>
      {stop ? (
        <StopSheet
          onClose={() => {
            setStop(false);
          }}
        />
      ) : null}
    </div>
  );
}

function Kv({ k, v }: { k: string; v: string }) {
  return (
    <span className={styles.kv}>
      <span className="t-caption c-muted">{k}</span>
      <strong className="t-body-strong">{v}</strong>
    </span>
  );
}

function SideTag({ side }: { side: 'buy' | 'sell' }) {
  return (
    <span className={clsx(styles.side, side === 'buy' ? styles.buy : styles.sell, 't-caption')}>
      {t.side[side]}
    </span>
  );
}

// ── V2-32 멈추기 ─────────────────────────────────────────────────────────────

export function StopSheet({ onClose }: { onClose: () => void }) {
  const [pick, setPick] = useState<'pause' | 'end' | 'sellAll'>('pause');
  const [error, setError] = useState<string | null>(null);
  const refresh = useLiveRefresh();
  const st = t.stop;
  const opts = [
    ['pause', st.pause, st.pauseLine],
    ['end', st.end, st.endLine],
    ['sellAll', st.sellAll, st.sellAllLine],
  ] as const;
  return (
    <Sheet title={st.title} onClose={onClose}>
      <div className="stack-block">
        {opts.map(([k, title, line]) => (
          <label key={k} className={clsx(w.choice, pick === k && w.choiceOn)}>
            <span className={w.status}>
              <input
                type="radio"
                name="stop"
                checked={pick === k}
                onChange={() => {
                  setPick(k);
                }}
              />
              <strong className="t-body-strong">{title}</strong>
            </span>
            <span className="t-caption c-muted">{line}</span>
          </label>
        ))}
        <Note>{st.toss}</Note>
        {error ? <Box tone="error" title={error} strongTitle /> : null}
        <div className={w.buttons}>
          <Button className={w.grow} onClick={onClose}>
            {st.cancel}
          </Button>
          <Button
            kind="danger"
            className={w.grow}
            onClick={() => {
              const call =
                pick === 'pause' ? liveApi.pause : pick === 'end' ? liveApi.end : liveApi.sellAll;
              call()
                .then(async () => {
                  await refresh();
                  onClose();
                })
                .catch((e: unknown) => {
                  setError(errorText(e));
                });
            }}
          >
            {st.go}
          </Button>
        </div>
      </div>
    </Sheet>
  );
}

// ── V2-11 계획 ───────────────────────────────────────────────────────────────

export function LivePlanScreen() {
  useDocumentTitle(copy.pages.plan);
  const s = useLive().data;
  const refresh = useLiveRefresh();
  const p = t.plan;
  if (!s) return null;
  if (!s.running)
    return <WizardPage title={p.title} main={<NotRunning s={s} />} side={<Note>{p.noRun}</Note>} />;
  const rows = s.plan_rows ?? [];
  const buys = rows.filter((r) => r.side === 'buy');
  const forD = s.next ? formatMonthDayWeekday(s.next.for_d) : '—';
  return (
    <WizardPage
      title={p.title}
      main={
        <>
          <p className={clsx(w.status, 't-heading-1')}>
            {p.head(forD, s.next ? formatMonthDayWeekday(s.next.judged) : '—')} <StateChip s={s} />
          </p>
          <div className={styles.grid4}>
            <Panel>
              <Kv k={p.buys} v={t.stocks(buys.length)} />
            </Panel>
            <Panel>
              <Kv k={p.maxAmount} v={formatKrw(buys.reduce((a, r) => a + (r.max ?? 0), 0))} />
            </Panel>
            <Panel>
              <Kv k={p.estAmount} v={formatKrw(buys.reduce((a, r) => a + (r.est ?? 0), 0))} />
            </Panel>
            <Panel>
              <Kv k={p.sells} v={t.stocks(rows.length - buys.length)} />
            </Panel>
          </div>
          <Panel title={p.orders(forD)}>
            <p className="t-caption c-muted">{p.rule}</p>
            {rows.length === 0 ? <p className="t-body c-muted">{p.noPlan}</p> : null}
            {rows.map((r) => (
              <div key={r.sym + r.side} className={styles.planRow}>
                <span>
                  <SideTag side={r.side} /> <strong className="t-body-strong">{r.name}</strong>
                  <br />
                  <span className="t-caption c-muted">{r.reason.join(' · ')}</span>
                </span>
                <span className="t-body">
                  {r.qty}
                  {t.shares}
                </span>
                <span className="t-body">{r.cap ? formatKrw(r.cap) : p.sellFloor}</span>
                <strong className="t-body">{r.max ? formatKrw(r.max) : '—'}</strong>
                <span className="t-body">{r.est ? formatKrw(r.est) : '—'}</span>
                <span className="t-caption c-muted">{p.planned}</span>
              </div>
            ))}
          </Panel>
          <Panel title={p.watching((s.watch ?? []).length)}>
            {(s.watch ?? []).map((x) => (
              <div key={x.sym} className={w.kv}>
                <strong className="t-body-strong">{x.name}</strong>
                <span className="t-body">
                  {x.levels
                    .map((l) =>
                      l.item === 'stop_loss'
                        ? p.stopWatch(formatKrw(l.trigger))
                        : l.item === 'take_profit'
                          ? p.takeWatch(formatKrw(l.trigger))
                          : p.trailWatch(formatKrw(l.trigger)),
                    )
                    .join(' · ')}
                  {x.price ? ` · ${p.now(formatKrw(x.price))}` : ''}
                </span>
              </div>
            ))}
          </Panel>
        </>
      }
      side={
        <>
          <Panel title={p.pauseTitle}>
            <p className="t-caption c-muted">{p.pauseLine}</p>
            {s.paused ? (
              <Button onClick={() => void liveApi.resume().then(refresh)}>{p.resumeButton}</Button>
            ) : (
              <TextLink onClick={() => void liveApi.pause().then(refresh)}>
                {p.pauseButton}
              </TextLink>
            )}
          </Panel>
          <Panel title={p.scheduleTitle(forD)}>
            {p.schedule.map((x) => (
              <Status key={x} kind="wait">
                {x}
              </Status>
            ))}
          </Panel>
        </>
      }
    />
  );
}

// ── V2-12 기록 ───────────────────────────────────────────────────────────────

export function LiveHistoryScreen() {
  useDocumentTitle(copy.pages.history);
  const s = useLive().data;
  const [filter, setFilter] = useState(0);
  const h = t.history;
  if (!s) return null;
  const rows = (s.history ?? []).filter((r) =>
    filter === 0
      ? true
      : filter === 1
        ? r.status.includes(h.filters[1])
        : filter === 2
          ? r.status === h.filters[2]
          : r.reason.includes(h.filters[3]),
  );
  const evalPnl = (s.holdings ?? []).reduce((a, x) => a + x.pnl, 0);
  return (
    <div className={w.page}>
      <h1 className="t-title">{h.title}</h1>
      {s.running ? (
        <p className={w.status}>
          <StateChip s={s} />
          <span className="t-caption c-muted">
            {s.strategy?.name} · {t.version(s.strategy?.version_no ?? 0)}
          </span>
        </p>
      ) : null}
      <div className={styles.grid4}>
        <Panel>
          <Kv k={h.realized} v={formatKrwSigned(s.realized ?? 0)} />
        </Panel>
        <Panel>
          <Kv k={h.trades} v={h.tradesValue(s.trades ?? 0, s.orders_n ?? 0)} />
        </Panel>
        <Panel>
          <Kv k={h.evalPnl} v={formatKrwSigned(evalPnl)} />
        </Panel>
      </div>
      <Panel
        action={
          <Button onClick={() => void download('/api/history/csv', 'history.csv')}>{h.csv}</Button>
        }
        title={
          <span className={styles.chips}>
            {h.filters.map((f, i) => (
              <button
                key={f}
                type="button"
                className={clsx(styles.filter, i === filter && styles.filterOn, 't-caption')}
                onClick={() => {
                  setFilter(i);
                }}
              >
                {f}
              </button>
            ))}
          </span>
        }
      >
        {rows.length === 0 ? <p className="t-body c-muted">{h.empty}</p> : null}
        {rows.map((r, i) => (
          <div key={`${r.d}${r.symbol}${String(i)}`} className={styles.histRow}>
            <span className="t-caption c-muted">{formatMonthDayWeekday(r.d)}</span>
            <span className="t-body">
              {r.name} <SideTag side={r.side === t.side.buy ? 'buy' : 'sell'} />
            </span>
            <span className="t-body">{r.price ? formatKrw(r.price) : '—'}</span>
            <span className="t-body">
              {r.qty}
              {t.shares}
            </span>
            <span className={clsx('t-body', r.pnl ? signClass(r.pnl) : undefined)}>
              {r.pnl === null ? '—' : formatKrwSigned(r.pnl)}
            </span>
            <span className="t-caption">{r.status}</span>
            <span className="t-caption c-muted">{r.reason}</span>
          </div>
        ))}
        <p className="t-caption c-muted">{h.foot}</p>
      </Panel>
    </div>
  );
}

// ── V2-13 할 일 · 알림 · V2-14 상세 ──────────────────────────────────────────

export function TodosScreen() {
  useDocumentTitle(t.todos.title);
  const s = useLive().data;
  const [tab, setTab] = useState<'todo' | 'alert'>('todo');
  const [open, setOpen] = useState<number | null>(null);
  const x = t.todos;
  if (!s) return null;
  const groups = (['red', 'yellow', 'info'] as const).map((sev) => ({
    sev,
    items: s.todos.filter((d) => d.severity === sev),
  }));
  return (
    <div className={w.page}>
      <h1 className="t-title">{x.title}</h1>
      <span className={styles.chips}>
        {(['todo', 'alert'] as const).map((k) => (
          <button
            key={k}
            type="button"
            className={clsx(styles.filter, tab === k && styles.filterOn, 't-caption')}
            onClick={() => {
              setTab(k);
            }}
          >
            {k === 'todo' ? x.tabTodo : x.tabAlert}
          </button>
        ))}
      </span>
      {tab === 'todo' ? (
        s.todos.length === 0 ? (
          <Panel>
            <p className="t-body c-muted">{x.none}</p>
          </Panel>
        ) : (
          groups
            .filter((g) => g.items.length)
            .map((g) => (
              <Panel key={g.sev} title={x[g.sev]}>
                {g.items.map((d) => (
                  <TodoRow
                    key={d.id}
                    d={d}
                    open={open === d.id}
                    onToggle={() => {
                      setOpen(open === d.id ? null : d.id);
                    }}
                  />
                ))}
              </Panel>
            ))
        )
      ) : (
        <Panel>
          {s.alerts.length === 0 ? <p className="t-body c-muted">{x.noAlerts}</p> : null}
          {s.alerts.map((a) => (
            <div key={a.id} className={w.kv}>
              <span className="t-body">
                <span className={clsx(styles.chip, 't-caption')}>{a.live ? x.live : x.paper}</span>{' '}
                {a.title}
              </span>
              <span className="t-caption c-muted">{formatMonthDayWeekday(a.at)}</span>
            </div>
          ))}
        </Panel>
      )}
      <Note>{x.tossStop}</Note>
    </div>
  );
}

function TodoRow({ d, open, onToggle }: { d: LiveTodo; open: boolean; onToggle: () => void }) {
  const refresh = useLiveRefresh();
  const [qty, setQty] = useState('');
  const [price, setPrice] = useState('');
  const [error, setError] = useState<string | null>(null);
  const a = t.todos.actions;
  const run = (p: Promise<unknown>) =>
    void p.then(refresh).catch((e: unknown) => {
      setError(errorText(e));
    });
  return (
    <div className={styles.todo}>
      <button type="button" className={clsx(styles.todoHead, 't-body-strong')} onClick={onToggle}>
        <span className={clsx(styles.dot, d.severity === 'red' ? styles.loss : styles.warnDot)}>
          ●
        </span>
        {d.title}
        <span className="t-caption c-muted">{formatMonthDayWeekday(d.created_at)}</span>
      </button>
      {open ? (
        <div className="stack-inline">
          {d.body ? <p className="t-caption c-muted">{d.body}</p> : null}
          {d.kind === 'mismatch' ? (
            <Button
              onClick={() => {
                run(liveApi.todo(d.id, 'match'));
              }}
            >
              {a.mismatch}
            </Button>
          ) : null}
          {d.kind === 'corp' ? (
            <Button
              onClick={() => {
                run(liveApi.todo(d.id, 'corp'));
              }}
            >
              {a.corp}
            </Button>
          ) : null}
          {d.kind === 'huge' || d.kind === 'too_big' ? (
            <Button
              onClick={() => {
                run(liveApi.todo(d.id, 'big-order'));
              }}
            >
              {a.huge}
            </Button>
          ) : null}
          {d.kind === 'unknown' ? (
            <>
              <TextField
                label={t.todos.filledQty}
                value={qty}
                inputMode="numeric"
                onChange={(e) => {
                  setQty(e.target.value);
                }}
              />
              <TextField
                label={t.todos.filledPrice}
                value={price}
                inputMode="numeric"
                onChange={(e) => {
                  setPrice(e.target.value);
                }}
              />
              <div className={w.buttons}>
                <Button
                  onClick={() => {
                    run(liveApi.todo(d.id, 'unknown', { filled_qty: 0 }));
                  }}
                >
                  {a.unknownNone}
                </Button>
                <Button
                  kind="primary"
                  disabled={!qty || !price}
                  onClick={() => {
                    run(
                      liveApi.todo(d.id, 'unknown', {
                        filled_qty: Number(qty),
                        price: Number(price),
                      }),
                    );
                  }}
                >
                  {a.unknownFilled}
                </Button>
              </div>
            </>
          ) : null}
          {error ? <Box tone="error" title={error} strongTitle /> : null}
        </div>
      ) : null}
    </div>
  );
}

// ── V2-30 실전 운용 시작 ─────────────────────────────────────────────────────

export function LiveStartScreen() {
  useDocumentTitle(t.start.title);
  const [params] = useSearchParams();
  const vid = Number(params.get('version') ?? 0);
  const pv = useLivePreview(vid).data;
  const navigate = useNavigate();
  const [amount, setAmount] = useState('10,000,000');
  const [risks, setRisks] = useState<boolean[]>([false, false, false, false]);
  const [noStop, setNoStop] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const st = t.start;
  if (!pv) return null;
  const ready = pv.ok && risks.every(Boolean) && (pv.has_stop || noStop);
  return (
    <WizardPage
      back={{ to: `/strategies`, label: copy.nav.strategies }}
      title={st.title}
      lead={`${pv.name} · ${t.version(pv.version_no)}`}
      main={
        <>
          <Panel title={st.checksTitle}>
            {pv.checks.map((c) => (
              <Status key={c.key} kind={c.ok ? 'ok' : 'bad'}>
                {st.checks[c.key]}
                {c.tail ? ` · ${c.tail}` : ''}
              </Status>
            ))}
          </Panel>
          <Panel title={st.amountTitle}>
            <TextField
              label={st.amountTitle}
              value={amount}
              inputMode="numeric"
              unit={t.won}
              onChange={(e) => {
                const n = Number(e.target.value.replace(/[^\d]/g, ''));
                setAmount(n ? n.toLocaleString() : '');
              }}
            />
          </Panel>
          <Panel title={st.limitsTitle}>
            <p className="t-body">{st.limits}</p>
          </Panel>
          <Panel title={st.execTitle}>
            <p className="t-body c-muted">{st.execLine}</p>
          </Panel>
          <Panel title={st.firstTitle}>
            <Note>{st.firstLine}</Note>
          </Panel>
          {pv.has_stop ? null : (
            <Box tone="error" icon="error" title={st.noStop} strongTitle>
              <Checkbox checked={noStop} onChange={setNoStop}>
                {st.noStopCheck}
              </Checkbox>
            </Box>
          )}
          <Panel title={st.riskTitle}>
            {st.risks.map((r, i) => (
              <Checkbox
                key={r}
                checked={risks[i] ?? false}
                onChange={(v) => {
                  setRisks(risks.map((x, j) => (j === i ? v : x)));
                }}
              >
                {r}
              </Checkbox>
            ))}
          </Panel>
          {error ? <Box tone="error" title={error} strongTitle /> : null}
          <Button
            kind="primary"
            className="full"
            disabled={!ready}
            onClick={() => {
              liveApi
                .start(vid, Number(amount.replace(/,/g, '')))
                .then(() => navigate('/'))
                .catch((e: unknown) => {
                  setError(errorText(e));
                });
            }}
          >
            {st.submit}
          </Button>
        </>
      }
    />
  );
}
