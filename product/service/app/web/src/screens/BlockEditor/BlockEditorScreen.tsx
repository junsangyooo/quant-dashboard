// 편집기 v2(그림 V2-23 · V2-24 · SPEC 4절): 단계 목록 · 캔버스(블록 · 선) · 오른쪽 패널 · 문제 목록.
// 규칙과 문제는 서버(/api/v2/analyze)가 셈하고, 선을 이을 때의 빨간 선만 화면이 먼저 보여요(model.ts).
import clsx from 'clsx';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  CircleHelp,
  FileText,
  GitBranch,
  Info,
  Maximize,
  Minus,
  Network,
  Pencil,
  Plus,
  Redo2,
  Undo2,
  X,
} from 'lucide-react';
import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import { useNavigate, useParams } from 'react-router';
import { isApiError } from '../../api/client';
import {
  useAnalysis,
  useCatalog,
  useSaveStrategy,
  useStrategyV2,
  type Block,
  type Body,
  type BodyView,
  type Catalog,
  type CatalogItem,
  type Problem,
  type Row,
  type StageId,
} from '../../api/v2';
import { Button } from '../../components/Buttons';
import { blockEditor as t } from '../../copy/blockEditor';
import { useMediaQuery as useMedia } from '../../lib/useMedia';
import { AddMenu } from './AddMenu';
import { BlockCard } from './BlockCard';
import {
  addBlockReason,
  autoLayout,
  blankBody,
  blockHeight,
  CARD_W,
  connect,
  edgeReason,
  History,
  isSellChain,
  josaRo,
  mergeSell,
  newBlock,
  newRow,
  removeBlock,
  stageCount,
  STAGES,
  updateBlock,
  withBlock,
} from './model';
import { PathsPanel, ProblemList, RowPanel, StartGuide } from './SidePanel';
import { StageGlyph } from './StageGlyph';
import styles from './BlockEditor.module.css';

const PLANE_TOP = 112;

interface DragState {
  kind: 'move' | 'link';
  id: string;
  dx: number;
  dy: number;
  x: number;
  y: number;
}

function Edges({ body, draft }: { body: Body; draft: DragState | null }) {
  const by = new Map(body.graph.blocks.map((b) => [b.id, b]));
  const path = (a: Block, b: Block) => {
    const x1 = a.x + CARD_W;
    const y1 = a.y + 20;
    const x2 = b.x;
    const y2 = b.y + 20;
    if (x2 < x1) {
      const mid = Math.max(a.y + blockHeight(a), y1) + 24;
      return `M${String(x1)},${String(y1)} H${String(x1 + 8)} V${String(mid)} H${String(x2 - 8)} V${String(y2)} H${String(x2)}`;
    }
    const c = Math.max(24, (x2 - x1) / 2);
    return `M${String(x1)},${String(y1)} C${String(x1 + c)},${String(y1)} ${String(x2 - c)},${String(y2)} ${String(x2)},${String(y2)}`;
  };
  return (
    <svg className={styles.edges} width="2400" height="2000" aria-hidden>
      {body.graph.edges.map((e) => {
        const a = by.get(e.from);
        const b = by.get(e.to);
        if (!a || !b) return null;
        const bad =
          edgeReason(
            { ...body, graph: { ...body.graph, edges: body.graph.edges.filter((x) => x !== e) } },
            e.from,
            e.to,
          ) !== null;
        return (
          <path
            key={`${e.from}-${e.to}`}
            d={path(a, b)}
            className={clsx(styles.edge, bad && styles.edgeBad)}
          />
        );
      })}
      {draft?.kind === 'link'
        ? (() => {
            const a = by.get(draft.id);
            if (!a) return null;
            return (
              <path
                d={`M${String(a.x + CARD_W)},${String(a.y + 20)} L${String(draft.x)},${String(draft.y)}`}
                className={clsx(styles.edge, styles.edgeDraft)}
              />
            );
          })()
        : null}
    </svg>
  );
}

function Palette({
  body,
  catalog,
  onAdd,
}: {
  body: Body;
  catalog: Catalog;
  onAdd: (stage: StageId) => void;
}) {
  return (
    <aside className={styles.palette}>
      <strong className="t-label">{t.stagesTitle(STAGES.length)}</strong>
      <p className={clsx(styles.muted, 't-caption')}>{t.stagesLead}</p>
      {catalog.stages.map((s) => {
        const n = stageCount(body, s.id);
        const full = s.once && n > 0;
        return (
          <button
            key={s.id}
            type="button"
            className={styles.paletteItem}
            disabled={addBlockReason(body.graph.blocks, s.id, s.name) !== null && !full}
            onClick={() => {
              onAdd(s.id);
            }}
            draggable={!full}
            onDragStart={(e) => {
              e.dataTransfer.setData('text/stage', s.id);
            }}
          >
            <span className={styles.muted}>{full ? '✓' : '⠿'}</span>
            <StageGlyph stage={s.id} />
            <span>
              <span className={styles.paletteName}>
                <span className="t-label">{`${s.circle} ${s.name}`}</span>
                <span className={clsx(styles.paletteCount, 't-caption')}>
                  {s.once ? t.onlyOne : t.placed(n)}
                </span>
              </span>
              <span className={clsx(styles.muted, 't-caption')}>{t.stageLines[s.id]}</span>
            </span>
          </button>
        );
      })}
    </aside>
  );
}

function NarrowView({
  body,
  catalog,
  view,
  version,
  onBack,
}: {
  body: Body;
  catalog: Catalog;
  view: BodyView | undefined;
  version: number;
  onBack: () => void;
}) {
  const stage = (id: StageId) => catalog.stages.find((x) => x.id === id);
  const order = [...body.graph.blocks].sort(
    (a, b) => STAGES.indexOf(a.stage) - STAGES.indexOf(b.stage),
  );
  return (
    <div className={styles.narrow}>
      <button type="button" className={clsx(styles.back, 't-caption')} onClick={onBack}>
        <ChevronLeft size={14} aria-hidden />
        {t.back}
      </button>
      <div className={styles.titleRow}>
        <h1 className={styles.title}>{body.name}</h1>
        {version ? (
          <span className={clsx(styles.versionChip, 't-caption')}>
            {t.versionChip(version, false)}
          </span>
        ) : null}
      </div>
      <div className={styles.tip}>
        <Info size={16} aria-hidden />
        <span>
          <strong className="t-label">{t.narrow.title}</strong>
          <br />
          <span className="t-caption">{t.narrow.line}</span>
        </span>
      </div>
      {view ? (
        <span className={clsx(styles.pill, 't-caption')}>
          {t.modeLabel} <strong>{view.analysis.mode_name}</strong>
        </span>
      ) : null}
      {view ? (
        <div className={styles.tip}>
          <span>
            <strong className="t-label">
              <FileText size={14} aria-hidden /> {t.sentenceTitle}
            </strong>
            <br />
            <span>{view.sentence}</span>
          </span>
        </div>
      ) : null}
      <div className={styles.sectionHead}>
        <strong className="t-label">{t.narrowOrder}</strong>
        {view ? (
          <span className={clsx(styles.muted, 't-caption')}>
            {t.narrowCounts(view.analysis.entry.length, view.analysis.sell.length)}
          </span>
        ) : null}
      </div>
      {order.map((b) => {
        const s = stage(b.stage);
        return (
          <div key={b.id}>
            {b.stage === 'sell' ? (
              <p className={clsx(styles.muted, 't-caption')}>{t.narrowSellLink}</p>
            ) : null}
            {b.stage === 'weight' ? (
              <p className={clsx(styles.muted, 't-caption')}>{t.narrowWeightLink}</p>
            ) : null}
            <div className={styles.narrowBlock}>
              <div className={styles.sectionHead}>
                <strong className="t-label">
                  <StageGlyph stage={b.stage} /> {s ? `${s.circle} ${s.name}` : b.stage}
                </strong>
                {s?.toggle ? <span className="t-caption">{t.match[b.match]}</span> : null}
              </div>
              {(view?.row_texts[b.id] ?? []).map((line, i) => {
                const chip = view?.chips[b.id]?.[i];
                return (
                  <span key={`${b.id}-${String(i)}`} className="t-caption">
                    {chip ? `${line} · ${chip.name}` : line}
                  </span>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function BlockEditorScreen() {
  const params = useParams();
  const id = params.id ? Number(params.id) : null;
  const catalogQ = useCatalog();
  const strategyQ = useStrategyV2(id);
  if (!catalogQ.data) return null;
  if (id === null)
    return <Editor key="new" id={null} catalog={catalogQ.data} initial={blankBody(t.newName)} />;
  if (!strategyQ.data) return null;
  return (
    <Editor
      key={`${String(id)}-${String(strategyQ.data.version.no)}`}
      id={id}
      catalog={catalogQ.data}
      initial={strategyQ.data.body}
    />
  );
}

function Editor({ id, catalog, initial }: { id: number | null; catalog: Catalog; initial: Body }) {
  const navigate = useNavigate();
  const strategyQ = useStrategyV2(id);
  const save = useSaveStrategy();
  const wide = useMedia('(min-width: 1024px)');
  const [body, setBody] = useState<Body>(initial);
  const [saved, setSaved] = useState<string>(() => JSON.stringify(initial));
  const [selected, setSelected] = useState<{ block: string; row: number | null } | null>(null);
  const [menu, setMenu] = useState<{ block: string; x: number; y: number } | null>(null);
  const [problemsOpen, setProblemsOpen] = useState(false);
  const [sentenceOpen, setSentenceOpen] = useState(false);
  const [chain, setChain] = useState<{ from: string; to: string } | null>(null);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [zoom, setZoom] = useState(1);
  const [, force] = useState(0);
  const [history] = useState(() => new History());
  const plane = useRef<HTMLDivElement>(null);

  const analysisQ = useAnalysis(body);
  const view = analysisQ.data;
  const changed = JSON.stringify(body) !== saved;

  const edit = (next: Body) => {
    history.push(body);
    setBody(next);
  };

  const problemsByBlock = useMemo(() => view?.analysis.problems ?? [], [view]);

  const version = strategyQ.data?.version.no ?? 0;
  const nextNo = id === null ? 1 : version + 1;
  const analysis = view?.analysis;
  const ok = analysis ? analysis.problems.length === 0 : true;

  const addStage = (stage: StageId, x?: number, y?: number) => {
    const s = catalog.stages.find((v) => v.id === stage);
    if (!s || addBlockReason(body.graph.blocks, stage, s.name)) return;
    const maxY = Math.max(0, ...body.graph.blocks.map((b) => b.y + blockHeight(b)));
    edit(withBlock(body, newBlock(body.graph.blocks, stage, x ?? 0, y ?? maxY + 24)));
  };

  const changeRow = (blockId: string, index: number, row: Row) => {
    edit(
      updateBlock(body, blockId, (b) => {
        b.rows[index] = row;
      }),
    );
  };

  const pick = (item: CatalogItem) => {
    if (!menu) return;
    const blockId = menu.block;
    const next = updateBlock(body, blockId, (b) => {
      b.rows.push(newRow(item));
    });
    edit(next);
    const b = next.graph.blocks.find((x) => x.id === blockId);
    setSelected({ block: blockId, row: (b?.rows.length ?? 1) - 1 });
    setMenu(null);
  };

  const local = (e: { clientX: number; clientY: number }) => {
    const r = plane.current?.getBoundingClientRect();
    return { x: (e.clientX - (r?.left ?? 0)) / zoom, y: (e.clientY - (r?.top ?? 0)) / zoom };
  };

  const startMove = (b: Block) => (e: ReactPointerEvent) => {
    const p = local(e);
    setDrag({ kind: 'move', id: b.id, dx: p.x - b.x, dy: p.y - b.y, x: p.x, y: p.y });
    setSelected({ block: b.id, row: null });
  };
  const startLink = (b: Block) => (e: ReactPointerEvent) => {
    e.stopPropagation();
    const p = local(e);
    setDrag({ kind: 'link', id: b.id, dx: 0, dy: 0, x: p.x, y: p.y });
  };
  const endLink = (target: Block) => () => {
    if (drag?.kind !== 'link') return;
    const reason = edgeReason(body, drag.id, target.id);
    setDrag(null);
    if (reason) return;
    if (isSellChain(body, drag.id, target.id)) {
      setChain({ from: drag.id, to: target.id });
      return;
    }
    edit(connect(body, drag.id, target.id));
  };

  const goProblem = (p: Problem) => {
    setProblemsOpen(false);
    if (p.block) setSelected({ block: p.block, row: p.row });
  };

  const doSave = () => {
    save.mutate(
      { id, body },
      {
        onSuccess: (r) => {
          setSaved(JSON.stringify(body));
          if (id === null) void navigate(`/strategies/${String(r.id)}/edit`, { replace: true });
        },
      },
    );
  };

  const selBlock = selected ? body.graph.blocks.find((b) => b.id === selected.block) : undefined;
  const rowIdx = selected?.row ?? null;
  const chips = view?.chips ?? {};
  const summaryBad = !ok;
  const running = strategyQ.data?.running ?? null;

  return (
    <div className={styles.page}>
      <div className={styles.head} hidden={!wide}>
        <div className={styles.headLeft}>
          <button
            type="button"
            className={clsx(styles.back, 't-caption')}
            onClick={() => void navigate(id === null ? '/strategies' : `/strategies/${String(id)}`)}
          >
            <ChevronLeft size={14} aria-hidden />
            {id === null ? t.back : body.name}
          </button>
          <div className={styles.titleRow}>
            <h1 className={styles.title}>{t.editTitle(body.name)}</h1>
            <span className={clsx(styles.versionChip, 't-caption')}>
              <Pencil size={12} aria-hidden />
              {id === null ? t.newChip(1) : t.versionChip(version, changed)}
            </span>
          </div>
          {running ? (
            <span className={clsx(styles.running, 't-caption')}>
              <Info size={12} aria-hidden />
              {t.runningNote(running.version_no)}
            </span>
          ) : null}
        </div>
        <div className={styles.headRight}>
          {analysis ? (
            <div style={{ position: 'relative' }}>
              <button
                type="button"
                className={clsx(styles.summary, summaryBad && styles.summaryBad)}
                aria-expanded={problemsOpen}
                onClick={() => {
                  setProblemsOpen(!problemsOpen);
                }}
              >
                {summaryBad ? (
                  <AlertTriangle size={18} aria-hidden />
                ) : (
                  <CheckCircle2 size={18} aria-hidden />
                )}
                <span className={styles.summaryLines}>
                  <span className="t-label">{analysis.summary.title}</span>
                  <span className="t-caption">{analysis.summary.line}</span>
                </span>
                {summaryBad ? <ChevronDown size={16} aria-hidden /> : null}
              </button>
              {problemsOpen && summaryBad ? (
                <div className={styles.problemsMenu}>
                  <strong className="t-label">{t.problemsHead(analysis.summary.title)}</strong>
                  <ProblemList
                    problems={analysis.problems}
                    warnings={analysis.warnings}
                    catalog={catalog}
                    onGo={goProblem}
                  />
                </div>
              ) : null}
            </div>
          ) : null}
          <Button
            disabled={!ok || changed || id === null}
            onClick={() => void navigate(`/strategies/${String(id)}/backtest`)}
          >
            {t.backtest}
          </Button>
          <Button kind="primary" disabled={!wide || save.isPending} onClick={doSave}>
            {t.save(nextNo, josaRo(nextNo))}
          </Button>
        </div>
      </div>
      {save.isError && isApiError(save.error) ? (
        <p className={styles.danger}>{save.error.message}</p>
      ) : null}
      {!wide ? (
        <NarrowView
          body={body}
          catalog={catalog}
          view={view}
          version={version}
          onBack={() => void navigate('/strategies')}
        />
      ) : (
        <div className={styles.body}>
          <Palette
            body={body}
            catalog={catalog}
            onAdd={(s) => {
              addStage(s);
            }}
          />
          <div className={styles.canvasWrap}>
            <div className={styles.canvasTop}>
              <div className={styles.pillRow}>
                <span className={clsx(styles.pill, 't-caption')}>
                  {t.modeLabel} <strong>{analysis?.mode_name ?? ''}</strong>{' '}
                  <Info size={12} aria-hidden />
                </span>
                <button
                  type="button"
                  className={clsx(styles.pill, styles.pillPlain, 't-caption')}
                  aria-expanded={sentenceOpen}
                  onClick={() => {
                    setSentenceOpen(!sentenceOpen);
                  }}
                >
                  <FileText size={14} aria-hidden />
                  {t.sentenceButton}
                </button>
              </div>
              <span className={clsx(styles.pathHelp, 't-caption')}>
                <Network size={14} aria-hidden />
                {t.pathHelp}
              </span>
              {sentenceOpen ? (
                <div className={styles.sentence} role="dialog" aria-label={t.sentenceTitle}>
                  <div className={styles.sectionHead}>
                    <strong className={styles.sideTitle}>
                      <FileText size={16} aria-hidden /> {t.sentenceTitle}
                    </strong>
                    <button
                      type="button"
                      aria-label={t.close}
                      onClick={() => {
                        setSentenceOpen(false);
                      }}
                    >
                      <X size={16} aria-hidden />
                    </button>
                  </div>
                  <p>{view?.sentence ?? ''}</p>
                  <p className={clsx(styles.muted, 't-caption')}>{t.sentenceFoot}</p>
                </div>
              ) : null}
            </div>
            <div
              className={styles.canvas}
              role="presentation"
              onDragOver={(e) => {
                e.preventDefault();
              }}
              onDrop={(e) => {
                const stage = STAGES.find((s) => s === e.dataTransfer.getData('text/stage'));
                if (stage === undefined) return;
                const p = local(e);
                addStage(stage, Math.max(0, p.x - CARD_W / 2), Math.max(0, p.y - 20));
              }}
              onPointerMove={(e) => {
                if (!drag) return;
                const p = local(e);
                if (drag.kind === 'move') {
                  setBody(
                    updateBlock(body, drag.id, (b) => {
                      b.x = Math.max(0, Math.round(p.x - drag.dx));
                      b.y = Math.max(0, Math.round(p.y - drag.dy));
                    }),
                  );
                } else setDrag({ ...drag, x: p.x, y: p.y });
              }}
              onPointerUp={() => {
                setDrag(null);
              }}
            >
              <div
                ref={plane}
                className={styles.plane}
                style={{
                  transform: `scale(${String(zoom)})`,
                  width: 2400,
                  height: 2000,
                  marginTop: PLANE_TOP,
                  marginLeft: 16,
                }}
              >
                <Edges body={body} draft={drag} />
                {!body.graph.blocks.some((b) => b.stage === 'signal') &&
                body.graph.blocks.length <= 4 ? (
                  <div className={clsx(styles.drop, 't-caption')} style={{ left: 152, top: 156 }}>
                    <StageGlyph stage="signal" />
                    {t.dropSignal}
                  </div>
                ) : null}
                {!body.graph.blocks.some((b) => b.stage === 'sell') &&
                body.graph.blocks.length <= 4 ? (
                  <div className={clsx(styles.drop, 't-caption')} style={{ left: 608, top: 156 }}>
                    <StageGlyph stage="sell" />
                    {t.dropSell}
                  </div>
                ) : null}
                {body.graph.blocks.map((b) => (
                  <BlockCard
                    key={b.id}
                    block={b}
                    catalog={catalog}
                    chips={chips[b.id] ?? []}
                    problems={problemsByBlock}
                    selected={selected?.block === b.id}
                    selectedRow={selected?.block === b.id ? selected.row : null}
                    onSelectRow={(row) => {
                      setSelected({ block: b.id, row });
                    }}
                    onChangeRow={(row, next) => {
                      changeRow(b.id, row, next);
                    }}
                    onMatch={(m) => {
                      edit(
                        updateBlock(body, b.id, (x) => {
                          x.match = m;
                        }),
                      );
                    }}
                    onAdd={() => {
                      setMenu({ block: b.id, x: Math.max(0, b.x - 328), y: b.y + 76 });
                    }}
                    onDragStart={startMove(b)}
                    onPortStart={startLink(b)}
                    onPortEnd={endLink(b)}
                  />
                ))}
                {menu
                  ? (() => {
                      const b = body.graph.blocks.find((x) => x.id === menu.block);
                      return b ? (
                        <AddMenu
                          block={b}
                          catalog={catalog}
                          x={menu.x}
                          y={menu.y}
                          onPick={pick}
                          onClose={() => {
                            setMenu(null);
                          }}
                        />
                      ) : null;
                    })()
                  : null}
              </div>
            </div>
            <div className={styles.toolbar}>
              <button
                type="button"
                className={clsx(styles.toolButton, 't-caption')}
                onClick={() => {
                  edit(autoLayout(body));
                }}
              >
                <GitBranch size={14} aria-hidden />
                {t.toolbar.arrange}
              </button>
              <button
                type="button"
                className={styles.toolButton}
                aria-label={t.toolbar.undo}
                disabled={!history.canUndo}
                onClick={() => {
                  const prev = history.undo(body);
                  if (prev) setBody(prev);
                  force((n) => n + 1);
                }}
              >
                <Undo2 size={16} aria-hidden />
              </button>
              <button
                type="button"
                className={styles.toolButton}
                aria-label={t.toolbar.redo}
                disabled={!history.canRedo}
                onClick={() => {
                  const next = history.redo(body);
                  if (next) setBody(next);
                  force((n) => n + 1);
                }}
              >
                <Redo2 size={16} aria-hidden />
              </button>
              <button
                type="button"
                className={styles.toolButton}
                aria-label={t.toolbar.zoomOut}
                onClick={() => {
                  setZoom(Math.max(0.5, zoom - 0.1));
                }}
              >
                <Minus size={16} aria-hidden />
              </button>
              <span className="t-caption">{`${String(Math.round(zoom * 100))}%`}</span>
              <button
                type="button"
                className={styles.toolButton}
                aria-label={t.toolbar.zoomIn}
                onClick={() => {
                  setZoom(Math.min(1.5, zoom + 0.1));
                }}
              >
                <Plus size={16} aria-hidden />
              </button>
              <button
                type="button"
                className={clsx(styles.toolButton, 't-caption')}
                onClick={() => {
                  setZoom(1);
                }}
              >
                <Maximize size={14} aria-hidden />
                {t.toolbar.fit}
              </button>
              <button type="button" className={styles.toolButton} aria-label={t.toolbar.help}>
                <CircleHelp size={16} aria-hidden />
              </button>
            </div>
          </div>
          <aside className={styles.side}>
            {selBlock && rowIdx !== null ? (
              <RowPanel
                block={selBlock}
                index={rowIdx}
                catalog={catalog}
                effectiveExec={chips[selBlock.id]?.[rowIdx]?.exec ?? null}
                onChange={(row) => {
                  changeRow(selBlock.id, rowIdx, row);
                }}
                onDelete={() => {
                  edit(
                    updateBlock(body, selBlock.id, (b) => {
                      b.rows.splice(rowIdx, 1);
                    }),
                  );
                  setSelected(null);
                }}
                onClose={() => {
                  setSelected(null);
                }}
              />
            ) : !body.graph.blocks.some((b) => b.stage === 'signal' || b.stage === 'sell') &&
              analysis ? (
              <StartGuide
                problems={analysis.problems}
                warnings={analysis.warnings}
                summaryTitle={analysis.summary.title}
                catalog={catalog}
                onGo={goProblem}
              />
            ) : view ? (
              <PathsPanel
                body={body}
                catalog={catalog}
                analysis={view.analysis}
                rowTexts={view.row_texts}
              />
            ) : null}
            {selBlock && selected?.row === null ? (
              <button
                type="button"
                className={styles.danger}
                onClick={() => {
                  edit(removeBlock(body, selBlock.id));
                  setSelected(null);
                }}
              >
                {t.deleteBlock}
              </button>
            ) : null}
          </aside>
        </div>
      )}
      {chain ? (
        <div className={styles.dialogBack}>
          <div className={styles.dialog} role="alertdialog" aria-label={t.chainConfirm.title}>
            <strong className={styles.sideTitle}>{t.chainConfirm.title}</strong>
            <p className={styles.muted}>{t.chainConfirm.line}</p>
            <div className={styles.dialogButtons}>
              <Button
                onClick={() => {
                  edit(connect(body, chain.from, chain.to));
                  setChain(null);
                }}
              >
                {t.chainConfirm.connect}
              </Button>
              <Button
                kind="primary"
                onClick={() => {
                  edit(mergeSell(body, chain.from, chain.to));
                  setChain(null);
                }}
              >
                {t.chainConfirm.merge}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
