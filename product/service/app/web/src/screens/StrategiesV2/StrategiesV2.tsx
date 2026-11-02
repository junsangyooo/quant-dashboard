// 전략 목록 · 새 전략 시트 · 붙여 넣기 · 상세(그림 V2-20 · V2-21 · V2-22 · V2-25).
import clsx from 'clsx';
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Copy,
  FileText,
  GitCommitHorizontal,
  Info,
  MinusCircle,
  Plus,
  X,
} from 'lucide-react';
import { useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { isApiError } from '../../api/client';
import {
  acceptImport,
  copyText,
  deleteStrategy,
  exportFile,
  importFile,
  previewImport,
  useCatalog,
  useStrategyDetail,
  useStrategyList,
  type Catalog,
  type ImportPreview,
  type StageId,
} from '../../api/v2';
import { Button } from '../../components/Buttons';
import { strategyV2 as t } from '../../copy/strategyV2';
import { blockEditor as be } from '../../copy/blockEditor';
import { josaRo } from '../BlockEditor/model';
import { StageGlyph } from '../BlockEditor/StageGlyph';
import styles from './StrategiesV2.module.css';

const stageLabel = (catalog: Catalog | undefined, s: StageId) => {
  const st = catalog?.stages.find((x) => x.id === s);
  return st ? `${st.circle} ${st.name}` : s;
};

function NewSheet({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const file = useRef<HTMLInputElement>(null);
  const [error, setError] = useState('');
  const options = [
    { key: 'blank', icon: Plus, ...t.blank, to: '/strategies/new' },
    { key: 'paste', icon: Copy, ...t.paste, to: '/strategies/import' },
    { key: 'file', icon: FileText, ...t.file, to: '' },
  ];
  function go(to: string) {
    if (to) void navigate(to);
    else file.current?.click();
  }
  return (
    <div className={styles.back}>
      <div className={styles.sheet} role="dialog" aria-label={t.sheetTitle}>
        <div className={styles.rowBetween}>
          <strong className="t-heading-1">{t.sheetTitle}</strong>
          <button type="button" aria-label={t.close} onClick={onClose}>
            <X size={20} aria-hidden />
          </button>
        </div>
        {options.map((o) => (
          <button
            key={o.key}
            type="button"
            className={styles.option}
            onClick={() => {
              go(o.to);
            }}
          >
            <span className={styles.optionIcon}>
              <o.icon size={18} aria-hidden />
            </span>
            <span className={styles.optionText}>
              <strong className="t-body-strong">{o.title}</strong>
              <span className={clsx(styles.muted, 't-caption')}>{o.line}</span>
            </span>
            <ChevronRight size={16} aria-hidden />
          </button>
        ))}
        <input
          ref={file}
          type="file"
          accept=".json,application/json"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            void f.text().then((text) =>
              importFile(text)
                .then((r) => navigate(`/strategies/${String(r.id)}/edit`))
                .catch((err: unknown) => {
                  setError(isApiError(err) ? err.message : String(err));
                }),
            );
          }}
        />
        {error ? <p className={styles.error}>{error}</p> : null}
        <div className={clsx(styles.note, 't-caption')}>
          <AlertTriangle size={16} aria-hidden />
          {t.labNote}
        </div>
      </div>
    </div>
  );
}

export function StrategiesListScreen() {
  const list = useStrategyList();
  const navigate = useNavigate();
  const [sheet, setSheet] = useState(false);
  const items = list.data?.strategies ?? [];
  return (
    <div className={styles.page}>
      <div className={styles.rowBetween}>
        <h1 className={styles.title}>
          {t.title} <span className={clsx(styles.muted, 't-body')}>{t.count(items.length)}</span>
        </h1>
        <div className={styles.buttons}>
          <Button onClick={() => void navigate('/strategies/import')}>{t.import}</Button>
          <Button
            kind="primary"
            onClick={() => {
              setSheet(true);
            }}
          >
            {t.newButton}
          </Button>
        </div>
      </div>
      {list.data && items.length === 0 ? (
        <div className={styles.empty}>
          <strong className="t-heading-1">{t.emptyTitle}</strong>
          <p className={styles.muted}>{t.emptyLine}</p>
        </div>
      ) : null}
      <div className={styles.grid}>
        {items.map((s) => (
          <button
            key={s.id}
            type="button"
            className={styles.card}
            onClick={() => void navigate(`/strategies/${String(s.id)}`)}
          >
            <span className={styles.rowBetween}>
              <strong className="t-heading-1">{s.name}</strong>
              <ChevronRight size={18} aria-hidden />
            </span>
            <span className={styles.chips}>
              <span className={clsx(styles.chip, 't-caption')}>{s.mode_name}</span>
              {s.running?.kind === 'live' ? (
                <span className={clsx(styles.chip, styles.chipLive, 't-caption')}>
                  {t.chipLive}
                </span>
              ) : null}
              {s.running?.kind === 'paper' ? (
                <span className={clsx(styles.chip, styles.chipPaper, 't-caption')}>
                  {t.chipPaper}
                </span>
              ) : null}
              {s.problems ? (
                <span className={clsx(styles.chip, styles.chipBad, 't-caption')}>
                  {t.chipProblems(s.problems)}
                </span>
              ) : null}
            </span>
            <span className={clsx(styles.muted, 't-caption')}>
              {t.cardLine(s.version.no, s.version.backtested, s.version.saved_day)}
            </span>
          </button>
        ))}
      </div>
      {sheet ? (
        <NewSheet
          onClose={() => {
            setSheet(false);
          }}
        />
      ) : null}
    </div>
  );
}

function Cards({
  catalog,
  cards,
}: {
  catalog: Catalog | undefined;
  cards: { id: string; stage: StageId; match: string; lines: string[] }[];
}) {
  return (
    <>
      {cards.map((c) => (
        <div key={c.id} className={styles.block}>
          <div className={styles.rowBetween}>
            <strong className={clsx(styles.stageName, 't-label')}>
              <StageGlyph stage={c.stage} /> {stageLabel(catalog, c.stage)}
            </strong>
            {['signal', 'filter', 'sell'].includes(c.stage) ? (
              <span className="t-caption">{be.match[c.match as 'all' | 'any']}</span>
            ) : null}
          </div>
          {c.lines.map((l) => (
            <span key={l} className="t-caption">
              {l}
            </span>
          ))}
        </div>
      ))}
    </>
  );
}

export function PasteScreen() {
  const navigate = useNavigate();
  const catalog = useCatalog().data;
  const [text, setText] = useState('');
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [error, setError] = useState<{ message: string; detail?: string | undefined } | null>(null);
  const check = (value: string) => {
    setText(value);
    setPreview(null);
    setError(null);
    if (!value.trim()) return;
    previewImport(value)
      .then(setPreview)
      .catch((err: unknown) => {
        if (isApiError(err)) setError({ message: err.message, detail: err.body?.detail });
      });
  };
  return (
    <div className={styles.narrowPage}>
      <button
        type="button"
        className={clsx(styles.backLink, 't-caption')}
        onClick={() => void navigate('/strategies')}
      >
        <ChevronLeft size={14} aria-hidden />
        {t.pasteBack}
      </button>
      <h1 className={styles.title}>{t.pasteTitle}</h1>
      <div className={clsx(styles.note, 't-caption')}>
        <AlertTriangle size={16} aria-hidden />
        {t.labNote}
      </div>
      <textarea
        className={styles.paste}
        aria-label={t.pasteTitle}
        placeholder={t.pastePlaceholder}
        value={text}
        onChange={(e) => {
          check(e.target.value);
        }}
      />
      {error ? (
        <div className={styles.errorBox}>
          <strong className="t-label">{error.message}</strong>
        </div>
      ) : null}
      {preview ? (
        <div className={styles.confirm}>
          <strong className="t-heading-1">{t.confirmTitle}</strong>
          <div className={styles.kv}>
            <span className={styles.muted}>{t.name}</span>
            <strong>{preview.name}</strong>
          </div>
          <div className={styles.kv}>
            <span className={styles.muted}>{t.stages}</span>
            <strong>{t.stagesValue(preview.stages, preview.entry, preview.sell)}</strong>
          </div>
          <div className={styles.kv}>
            <span className={styles.muted}>{t.rows}</span>
            <strong>{t.rowsValue(preview.rows)}</strong>
          </div>
          <div className={styles.kv}>
            <span className={styles.muted}>{t.blanks}</span>
            <strong>{t.blanksValue(preview.blanks, preview.blank_kinds)}</strong>
          </div>
          <p className={clsx(styles.muted, 't-caption')}>{t.blanksLine}</p>
          <p className={clsx(styles.infoLine, 't-caption')}>
            <Info size={14} aria-hidden /> {t.cooldownNote}
          </p>
          <Cards catalog={catalog} cards={preview.cards} />
          <p className={clsx(styles.muted, 't-caption')}>
            {t.others(
              preview.others.length,
              preview.others.map((s) => stageLabel(catalog, s)).join(' · '),
            )}
          </p>
        </div>
      ) : null}
      <div className={styles.buttonsEnd}>
        <Button onClick={() => void navigate('/strategies')}>{t.cancel}</Button>
        <Button
          kind="primary"
          disabled={!preview}
          onClick={() => {
            void acceptImport(text).then((r) => navigate(`/strategies/${String(r.id)}/edit`));
          }}
        >
          {t.acceptEdit}
        </Button>
      </div>
    </div>
  );
}

function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function StrategyDetailScreen() {
  const params = useParams();
  const id = Number(params.id);
  const navigate = useNavigate();
  const catalog = useCatalog().data;
  const q = useStrategyDetail(id);
  const [notice, setNotice] = useState('');
  const d = q.data;
  if (!d) return null;
  const no = d.version.no;
  const ro = josaRo(no);
  const order: StageId[] = ['universe', 'signal', 'filter', 'select', 'buy', 'sell', 'weight'];
  const blocks = [...d.body.graph.blocks].sort(
    (a, b) => order.indexOf(a.stage) - order.indexOf(b.stage),
  );
  return (
    <div className={styles.page}>
      <button
        type="button"
        className={clsx(styles.backLink, 't-caption')}
        onClick={() => void navigate('/strategies')}
      >
        <ChevronLeft size={14} aria-hidden />
        {t.back}
      </button>
      <div className={styles.rowBetween}>
        <div className={styles.titleRow}>
          <h1 className={styles.title}>{d.name}</h1>
          <span className={clsx(styles.chip, 't-label')}>
            <GitCommitHorizontal size={14} aria-hidden /> {t.versionLabel(no)}
          </span>
          <span className={clsx(styles.chip, 't-caption')}>{d.analysis.mode_name}</span>
        </div>
        <div className={styles.buttons}>
          <Button
            onClick={() =>
              void exportFile(id).then((f) => {
                download(f.name, f.text);
              })
            }
          >
            {t.exportFile}
          </Button>
          <Button
            onClick={() =>
              void copyText(id)
                .then((c) => navigator.clipboard.writeText(c.text))
                .then(() => {
                  setNotice(t.copied);
                })
            }
          >
            {t.copyStrategy}
          </Button>
          <Button onClick={() => void navigate(`/strategies/${String(id)}/backtest`)}>
            {t.backtest}
          </Button>
          <Button kind="primary" onClick={() => void navigate(`/strategies/${String(id)}/edit`)}>
            {t.edit}
          </Button>
        </div>
      </div>
      {notice ? <p className={clsx(styles.muted, 't-caption')}>{notice}</p> : null}
      <div className={styles.detail}>
        <div className={styles.detailMain}>
          <div className={styles.sentence}>
            <div className={styles.rowBetween}>
              <strong className={clsx(styles.stageName, 't-label')}>
                <FileText size={14} aria-hidden /> {t.sentence}
              </strong>
              <span className={clsx(styles.muted, 't-caption')}>{t.versionLabel(no)}</span>
            </div>
            <p>{d.sentence}</p>
          </div>
          <div className={styles.rowBetween}>
            <strong className="t-heading-1">{t.blocksTitle}</strong>
            <span className={clsx(styles.muted, 't-caption')}>
              {t.pathCount(d.analysis.entry.length, d.analysis.sell.length)}
            </span>
          </div>
          <div className={styles.blockGrid}>
            <Cards
              catalog={catalog}
              cards={blocks.map((b) => ({
                id: b.id,
                stage: b.stage,
                match: b.match,
                lines: d.block_lines[b.id] ?? [],
              }))}
            />
          </div>
        </div>
        <aside className={styles.detailSide}>
          <div className={styles.sideCard}>
            <strong className="t-heading-1">{t.liveTitle}</strong>
            <p className={clsx(styles.muted, 't-caption')}>{t.liveLine}</p>
            <Button
              kind="primary"
              block
              disabled={!d.version.backtested}
              onClick={() => void navigate(`/live/start?version=${String(d.version.id)}`)}
            >
              {t.liveButton(no, ro)}
            </Button>
          </div>
          <div className={styles.sideCard}>
            <strong className="t-heading-1">{t.paperTitle}</strong>
            <p className={clsx(styles.muted, 't-caption')}>{t.paperLine}</p>
            <Button
              block
              onClick={() => void navigate(`/paper/start?version=${String(d.version.id)}`)}
            >
              {t.paperButton(no, ro)}
            </Button>
          </div>
          <div className={styles.sideCard}>
            <strong className="t-heading-1">{t.versionsTitle}</strong>
            {d.versions.map((v) => (
              <div key={v.id} className={clsx(styles.versionRow, v.no === no && styles.versionNow)}>
                <span>
                  <strong className="t-label">{t.versionLabel(v.no)}</strong>
                  <br />
                  <span className={clsx(styles.muted, 't-caption')}>
                    {t.versionRow(v.saved_day, v.saved_hm, v.backtested ? v.backtested_hm : '')}
                  </span>
                </span>
                <span className={clsx(styles.chip, !v.backtested && styles.chipWarn, 't-caption')}>
                  {v.backtested ? t.tested : t.untested}
                </span>
              </div>
            ))}
          </div>
          {d.deletable ? (
            <button
              type="button"
              className={clsx(styles.danger, 't-label')}
              onClick={() => {
                if (window.confirm(t.deleteConfirm))
                  void deleteStrategy(id).then(() => navigate('/strategies'));
              }}
            >
              <MinusCircle size={16} aria-hidden /> {t.delete}
            </button>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
