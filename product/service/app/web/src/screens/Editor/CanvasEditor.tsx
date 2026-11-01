// 캔버스 편집(폭 1024 이상): 조건 목록 | 캔버스 | 오른쪽 패널. 상태 · 되돌리기 · 저장 · 나가기 확인.
import clsx from 'clsx';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react';
import { useBlocker, useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import {
  ChevronDown,
  CircleCheck,
  CircleHelp,
  CircleX,
  Info,
  Minus,
  Pencil,
  Plus,
  Redo2,
  Scan,
  MousePointer2,
  TriangleAlert,
  Undo2,
  Workflow,
} from 'lucide-react';
import { api, isApiError } from '../../api/client';
import type {
  Analysis,
  Body,
  Catalog,
  CheckResult2,
  Graph,
  GraphEdge,
  GraphNode,
  ParamValue,
  Problem,
  SlotKey,
} from '../../api/mvp';
import { Button } from '../../components/Buttons';
import { PathsPanel } from '../../components/graph/PathsPanel';
import { Sheet } from '../../components/Sheet';
import { editorCopy as t } from '../../copy/editor';
import { graphRules, kindNames, modeNames } from '../../copy/graph';
import {
  autoLayout,
  distanceTo,
  nodeTags,
  samplePath,
  wrapLayout,
  type Sizes,
} from '../../graph/layout';
import {
  analyze,
  edgeReason,
  josa,
  labelOf,
  linkReason,
  modeOf,
  pieceTitle,
  slotCircle,
  slotLabel,
  stageOf,
  type RuleCatalog,
} from '../../graph/rules';
import { pathText, problemParts, problemTone } from '../../graph/text';
import { BackLink } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';
import {
  Canvas,
  edgeGeom,
  nodeBox,
  type CanvasHandle,
  type Connecting,
  type DropState,
  type Selection,
  type View,
} from './Canvas';
import {
  addEdge,
  blankParams,
  changeCount,
  changes,
  historyOf,
  moveNode,
  newId,
  placeAll,
  push,
  redo,
  removeEdge,
  removeNode,
  ruleCatalog,
  setParam,
  splitEdge,
  undo,
  type History,
} from './model';
import { Palette } from './Palette';
import {
  AddPanel,
  ConnectInfo,
  DropInfo,
  EdgePanel,
  NodePanel,
  PathsSide,
  type AddOption,
  type NextOption,
} from './Panel';
import styles from './Editor.module.css';
import { J } from '../../copy/particles';

interface Toast {
  text: string;
  action?: 'undo' | 'backtest';
}

export interface EditorStart {
  /** 저장된 전략이면 id, 새 전략이면 null. */
  sid: number | null;
  /** 지금 버전 번호(새 전략은 null). */
  no: number | null;
  body: Body;
  /** 처음 열 때 알림(저장 직후 '버전 1로 저장했어요'). */
  toast?: string | null;
}

const KEEP_SIZES: Sizes = {};
const STAGE_INDEX: Record<SlotKey, number> = {
  universe: 0,
  signal: 1,
  filter: 2,
  select: 3,
  buy: 4,
  sell: 5,
  weight: 6,
};

/** 위치가 없는 조건(옛 일곱 칸 · 붙여 넣은 글)은 두 줄 배치로 놓는다. */
export function withPositions(cat: RuleCatalog, g: Graph): Graph {
  if (g.nodes.every((n) => n.x !== null && n.y !== null)) return g;
  return placeAll(g, wrapLayout(cat, g, KEEP_SIZES));
}

function keyOf(g: Graph) {
  return JSON.stringify(g);
}

export function CanvasEditor({ catalog, start }: { catalog: Catalog; start: EditorStart }) {
  const cat = useMemo(() => ruleCatalog(catalog), [catalog]);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [sid, setSid] = useState(start.sid);
  const [savedNo, setSavedNo] = useState(start.no);
  const [saved, setSaved] = useState<Body>(() => ({
    ...start.body,
    graph: withPositions(cat, start.body.graph),
  }));
  const name = saved.name;
  const [hist, setHist] = useState<History>(() => historyOf(saved.graph));
  const graph = hist.now;
  const [sel, setSel] = useState<Selection>(null);
  const [sizes, setSizes] = useState<Sizes>({});
  const [view, setView] = useState<View>({ x: 0, y: 0, z: 1 });
  const [problemsOpen, setProblemsOpen] = useState(false);
  const [nextOpen, setNextOpen] = useState(false);
  const [focusField, setFocusField] = useState<string | null>(null);
  const [hot, setHot] = useState<{ key: string; nodes: Set<string> } | null>(null);
  const [toast, setToast] = useState<Toast | null>(
    start.toast ? { text: start.toast, action: 'backtest' } : null,
  );
  const [tip, setTip] = useState<string | null>(null);
  const [conn, setConn] = useState<Connecting | null>(null);
  const [drag, setDrag] = useState<{
    piece: string;
    sx: number;
    sy: number;
    active: boolean;
    cx: number;
    cy: number;
    /** 캔버스 안이면 캔버스 좌표(포인터 움직일 때 잰다). */
    w: { x: number; y: number } | null;
  } | null>(null);
  const [adding, setAdding] = useState<{
    piece: string;
    choice: string;
    around: string | null;
  } | null>(null);
  const [showKeys, setShowKeys] = useState(false);
  const [middleNote, setMiddleNote] = useState(false);
  const [showMode, setShowMode] = useState(false);
  const [server, setServer] = useState<{ key: string; analysis: Analysis } | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const chainShown = useRef(false);
  const leaving = useRef(false);
  const canvasRef = useRef<CanvasHandle>(null);
  /** 선 위에 놓은 뒤 화면을 맞출 그래프(다음 그리기 뒤에 맞춘다). */
  const pendingFit = useRef<Graph | null>(null);
  const toastTimer = useRef<number | null>(null);

  useDocumentTitle(t.title(name || t.newTitle));

  const local = useMemo(() => analyze(cat, graph), [cat, graph]);
  const gkey = keyOf(graph);
  // 화면은 서버의 검사 결과를 그대로 보인다. 답이 오기 전에는 같은 규칙의 화면 계산(시험으로 서버와 같음을 고정)
  const analysis = server?.key === gkey ? server.analysis : local;
  const draft: Body = { name, graph };
  const ch = changes(saved, draft);
  const dirty = sid === null || changeCount(ch) > 0;
  const isNew = sid === null;

  useEffect(() => {
    const body: Body = { name: name || t.newTitle, graph };
    const key = keyOf(graph);
    const timer = window.setTimeout(() => {
      api
        .post<CheckResult2>(`/api/strategies/${String(sid ?? 0)}/check`, { body })
        .then((r) => {
          setServer({ key, analysis: r.analysis });
        })
        .catch(() => undefined);
    }, 180);
    return () => {
      window.clearTimeout(timer);
    };
  }, [graph, name, sid]);

  const say = useCallback((next: Toast | null, ms = 6000) => {
    if (toastTimer.current) window.clearTimeout(toastTimer.current);
    setToast(next);
    if (next)
      toastTimer.current = window.setTimeout(() => {
        setToast(null);
      }, ms);
  }, []);

  // ── 그래프 바꾸기(되돌리기 기록 · 방식 바뀜 알림) ──────────────────────────────
  const commit = (next: Graph, key: string | null = null, note?: string) => {
    const before = modeOf(cat, graph);
    const after = modeOf(cat, next);
    setMiddleNote(false);
    setHist(push(hist, next, key));
    if (before !== after && after !== null) {
      const a = analyze(cat, next);
      const need = a.problems.filter((p) => p.kind === 'required').length;
      const cannot = a.problems.filter((p) => p.kind === 'unusable').length;
      say({ text: t.mode.changed(josa(modeNames[after], J.ro), need, cannot), action: 'undo' });
    } else if (note) say({ text: note, action: 'undo' });
  };

  const node = (id: string) => graph.nodes.find((n) => n.id === id);
  const selNode = sel?.kind === 'node' ? node(sel.id) : undefined;

  const select = (s: Selection) => {
    setSel(s);
    setNextOpen(false);
    setFocusField(null);
    setAdding(null);
    if (s) setProblemsOpen(false);
  };

  const removeSelected = () => {
    if (sel?.kind === 'node') {
      const n = node(sel.id);
      if (!n) return;
      const r = removeNode(graph, sel.id);
      const hadIn = graph.edges.some((e) => e.to === n.id);
      const hadOut = graph.edges.some((e) => e.from === n.id);
      commit(
        r.graph,
        null,
        hadIn && hadOut
          ? t.toast.removedWithLines(labelOf(cat, n))
          : t.toast.removed(labelOf(cat, n)),
      );
      setMiddleNote(hadIn && hadOut);
      setSel(null);
    } else if (sel?.kind === 'edge') {
      commit(removeEdge(graph, sel.edge), null, t.toast.edgeRemoved);
      setSel(null);
    }
  };

  const connect = (from: string, to: string) => {
    if (edgeReason(cat, graph, from, to) !== null) return;
    const next = addEdge(graph, from, to);
    const a = node(from);
    const b = node(to);
    const g1 = (s: SlotKey) =>
      s === 'signal' || s === 'filter' ? 'entry' : s === 'sell' ? 'sell' : '';
    let note: string | undefined;
    if (a && b && !chainShown.current) {
      const ga = g1(stageOf(cat, a.piece));
      if (ga && ga === g1(stageOf(cat, b.piece))) {
        chainShown.current = true;
        note = ga === 'sell' ? t.toast.chainSell : t.toast.chainEntry;
      }
    }
    commit(next, null, note);
  };

  // ── 선 위에 놓기 · 눌러서 추가 ──────────────────────────────────────────────
  const insertable = (piece: string): GraphEdge[] => {
    const s = stageOf(cat, piece);
    if (s === 'weight' || s === 'universe' || s === 'buy') return [];
    const hasSelect = s === 'select' || graph.nodes.some((n) => stageOf(cat, n.piece) === 'select');
    return graph.edges.filter((e) => {
      const a = node(e.from);
      const b = node(e.to);
      if (!a || !b) return false;
      const sa = stageOf(cat, a.piece);
      const sb = stageOf(cat, b.piece);
      if (sa === 'weight') return false;
      return linkReason(sa, s, hasSelect) === null && linkReason(s, sb, hasSelect) === null;
    });
  };

  const freeSpot = (x: number, y: number, g: Graph): { x: number; y: number } => {
    let yy = y;
    for (let k = 0; k < 12; k++) {
      const hit = g.nodes.some((n) => {
        const b = nodeBox(g, sizes, n.id);
        return (
          b && x < b.x + b.w + 10 && x + 150 > b.x - 10 && yy < b.y + b.h + 10 && yy + 64 > b.y - 10
        );
      });
      if (!hit) return { x: Math.round(x), y: Math.round(yy) };
      yy += 84;
    }
    return { x: Math.round(x), y: Math.round(yy) };
  };

  const makeNode = (piece: string, x: number, y: number): GraphNode => ({
    id: newId(catalog, graph, piece),
    piece,
    params: blankParams(catalog, piece),
    x: Math.round(x),
    y: Math.round(y),
  });

  const pathsWith = (e: GraphEdge) => {
    const has = (nodes: string[]) => nodes.some((id, i) => id === e.from && nodes[i + 1] === e.to);
    return {
      entry: analysis.entry.map((p, i) => ({ p, i })).filter((x) => has(x.p.nodes)),
      sell: analysis.sell.map((p, i) => ({ p, i })).filter((x) => has(x.p.nodes)),
    };
  };

  const pathLabel = (e: GraphEdge): string => {
    const w = pathsWith(e);
    if (w.entry[0]) return t.paths.entryRow(w.entry[0].i + 1);
    if (w.sell[0]) return t.paths.sellRow(w.sell[0].i + 1);
    return '';
  };

  const insertAt = (piece: string, e: GraphEdge | null, at?: { x: number; y: number }) => {
    let n: GraphNode;
    let next: Graph;
    if (e) {
      // 선 위에 놓기: 끝 조건 자리에 놓고, 그 오른쪽 조건들을 한 열 민다(자리가 넉넉하면 가운데에)
      const a = nodeBox(graph, sizes, e.from);
      const b = nodeBox(graph, sizes, e.to);
      const PITCH = 216;
      let x = 200;
      let y = 200;
      let shiftFrom: number | null = null;
      let band: { y: number } | null = null;
      if (a && b && b.x > a.x) {
        if (b.x - a.x >= PITCH * 2) {
          x = Math.round((a.x + b.x) / 2);
          y = Math.round((a.y + b.y) / 2);
        } else {
          x = b.x;
          y = Math.round(a.y + a.h / 2 - 32);
          shiftFrom = b.x - 4;
        }
      } else if (a) {
        x = a.x + PITCH;
        y = a.y;
        shiftFrom = a.x + 4;
        band = { y: a.y };
      }
      const moved: Graph = {
        nodes: graph.nodes.map((m) => {
          if (shiftFrom === null || m.x === null || m.y === null || m.x < shiftFrom) return m;
          if (band && Math.abs(m.y - band.y) > 140) return m;
          return { ...m, x: m.x + PITCH };
        }),
        edges: graph.edges,
      };
      n = makeNode(piece, x, y);
      next = splitEdge(moved, e, n);
      // 놓은 조건 · 밀린 조건이 캔버스 밖으로 나가면 화면을 맞춘다
      const movedIds = moved.nodes.filter((m, i) => m.x !== graph.nodes[i]?.x).map((m) => m.id);
      const r = canvasRef.current?.rect();
      const out = [n.id, ...movedIds].some((id) => {
        const b = nodeBox(next, sizes, id);
        if (!b || !r) return false;
        const sx = b.x * view.z + view.x;
        const sy = b.y * view.z + view.y;
        return (
          sx < 0 || sy < 60 || sx + b.w * view.z > r.width || sy + b.h * view.z > r.height - 70
        );
      });
      if (out) pendingFit.current = next;
    } else {
      const spot = freeSpot(at?.x ?? 200, at?.y ?? 200, graph);
      n = makeNode(piece, spot.x, spot.y);
      next = { nodes: [...graph.nodes, n], edges: graph.edges };
    }
    commit(next);
    setSel({ kind: 'node', id: n.id });
    setAdding(null);
    setNextOpen(false);
  };

  const addOptions = (
    piece: string,
    around: string | null = adding?.around ?? null,
  ): { head: string; options: AddOption[] } => {
    const s = stageOf(cat, piece);
    const list = insertable(piece);
    const near = around ? list.filter((e) => e.from === around) : [];
    // 고른 조건 뒤에 넣을 수 있는 선이 있으면 그 선들만
    const sorted = near.length > 0 ? near : list;
    const opts: AddOption[] = sorted.map((e) => {
      const a = node(e.from);
      const b = node(e.to);
      const label = pathLabel(e);
      return {
        key: `e:${e.from}>${e.to}`,
        kind: 'split',
        edge: e,
        title: t.add.between(
          a ? (labelOf(cat, a).split(' ')[0] ?? '') : '',
          b ? labelOf(cat, b) : '',
        ),
        line: label ? t.add.goesInto(label) : '',
      };
    });
    const buy = graph.nodes.find((n) => stageOf(cat, n.piece) === 'buy');
    if (buy && s === 'weight')
      opts.unshift({ key: 'toBuy', kind: 'toBuy', title: t.add.toBuy, line: t.add.toBuyLine });
    if (buy && s === 'sell')
      opts.push({
        key: 'afterBuy',
        kind: 'afterBuy',
        title: t.add.afterBuy,
        line: t.add.afterBuyLine,
      });
    opts.push({ key: 'free', kind: 'free', title: t.add.free, line: t.add.freeLine });
    const fromSel = near.length;
    const aroundNode = around ? node(around) : undefined;
    const head =
      aroundNode && fromSel >= 2 ? t.add.split(labelOf(cat, aroundNode), fromSel) : t.add.which;
    return { head, options: opts };
  };

  const doAdd = () => {
    if (!adding) return;
    const { options } = addOptions(adding.piece);
    const o = options.find((x) => x.key === adding.choice) ?? options[0];
    if (!o) return;
    const buy = graph.nodes.find((n) => stageOf(cat, n.piece) === 'buy');
    const bb = buy ? nodeBox(graph, sizes, buy.id) : null;
    if (o.kind === 'split' && o.edge) insertAt(adding.piece, o.edge);
    else if (o.kind === 'toBuy' && buy && bb) {
      const spot = freeSpot(bb.x - 216, bb.y + bb.h + 60, graph);
      const n = makeNode(adding.piece, spot.x, spot.y);
      commit({ nodes: [...graph.nodes, n], edges: [...graph.edges, { from: n.id, to: buy.id }] });
      setSel({ kind: 'node', id: n.id });
      setAdding(null);
    } else if (o.kind === 'afterBuy' && buy && bb) {
      const spot = freeSpot(bb.x + 216, bb.y, graph);
      const n = makeNode(adding.piece, spot.x, spot.y);
      commit({ nodes: [...graph.nodes, n], edges: [...graph.edges, { from: buy.id, to: n.id }] });
      setSel({ kind: 'node', id: n.id });
      setAdding(null);
    } else {
      const r = canvasRef.current?.rect();
      const cx = r ? (r.width / 2 - view.x) / view.z - 75 : 200;
      const cy = r ? (r.height / 2 - view.y) / view.z - 30 : 200;
      insertAt(adding.piece, null, { x: cx, y: cy });
    }
  };

  // ── 조건 끌어 오기(목록 → 캔버스) ─────────────────────────────────────────────
  const onPalDown = (piece: string, e: ReactPointerEvent<HTMLButtonElement>) => {
    if (e.button !== 0) return;
    setDrag({
      piece,
      sx: e.clientX,
      sy: e.clientY,
      active: false,
      cx: e.clientX,
      cy: e.clientY,
      w: null,
    });
  };

  const nearEdge = (piece: string, w: { x: number; y: number }): GraphEdge | null => {
    let near: GraphEdge | null = null;
    let best = 22 / view.z;
    for (const e of insertable(piece)) {
      const eg = edgeGeom(cat, graph, sizes, e);
      if (!eg) continue;
      const d = distanceTo(samplePath(eg.a, eg.b, eg.fromBelow, 24, eg.mid), w.x, w.y);
      if (d < best) {
        best = d;
        near = e;
      }
    }
    return near;
  };

  const dropState = (): DropState | null => {
    if (!drag?.active) return null;
    const w = drag.w;
    const spec = catalog.pieces[drag.piece];
    return {
      candidates: insertable(drag.piece),
      near: w ? nearEdge(drag.piece, w) : null,
      ghost:
        w && spec
          ? {
              x: w.x - 75,
              y: w.y - 28,
              title: pieceTitle(cat, {
                piece: drag.piece,
                params: blankParams(catalog, drag.piece),
              }),
              slot: spec.slot,
            }
          : null,
    };
  };
  const drop = dropState();
  const addDrop: DropState | null = (() => {
    if (!adding) return null;
    const { options } = addOptions(adding.piece);
    const edges = options.flatMap((o) => (o.edge ? [o.edge] : []));
    const chosen = options.find((o) => o.key === adding.choice)?.edge ?? null;
    return { candidates: edges, near: chosen, ghost: null };
  })();

  const finishDrag = (d: {
    piece: string;
    active: boolean;
    w: { x: number; y: number } | null;
  }) => {
    if (!d.active) {
      setProblemsOpen(false);
      const around = sel?.kind === 'node' ? sel.id : null;
      const { options } = addOptions(d.piece, around);
      setAdding({ piece: d.piece, choice: options[0]?.key ?? 'free', around });
      return;
    }
    const w = d.w;
    if (!w) return;
    const ds = { near: nearEdge(d.piece, w) };
    if (ds.near) insertAt(d.piece, ds.near);
    else {
      const n = makeNode(d.piece, w.x - 75, w.y - 28);
      commit({ nodes: [...graph.nodes, n], edges: graph.edges });
      setSel({ kind: 'node', id: n.id });
    }
  };

  useEffect(() => {
    if (!drag) return;
    const move = (e: PointerEvent) => {
      const r = canvasRef.current?.rect();
      const inside = r
        ? e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom
        : false;
      const w = inside ? (canvasRef.current?.toWorld(e.clientX, e.clientY) ?? null) : null;
      setDrag((d) => {
        if (!d) return d;
        const active = d.active || Math.abs(e.clientX - d.sx) + Math.abs(e.clientY - d.sy) > 5;
        return { ...d, active, cx: e.clientX, cy: e.clientY, w };
      });
    };
    const up = () => {
      setDrag((d) => {
        if (!d) return null;
        window.setTimeout(() => {
          finishDrag(d);
        }, 0);
        return null;
      });
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
  });

  // ── 잇기 ─────────────────────────────────────────────────────────────────
  const startConnect = (from: string, x: number, y: number) => {
    const ok = new Set(
      graph.nodes.filter((n) => edgeReason(cat, graph, from, n.id) === null).map((n) => n.id),
    );
    setConn({ from, x, y, over: null, ok, why: null });
    setSel(null);
  };
  const moveConnect = (x: number, y: number, over: string | null) => {
    setConn((c) =>
      c ? { ...c, x, y, over, why: over ? edgeReason(cat, graph, c.from, over) : null } : c,
    );
  };
  const endConnect = () => {
    if (conn?.over && conn.ok.has(conn.over)) connect(conn.from, conn.over);
    setConn(null);
  };

  // ── 보기 ─────────────────────────────────────────────────────────────────
  const fit = useCallback(
    (g: Graph = graph) => {
      const r = canvasRef.current?.rect();
      if (!r || g.nodes.length === 0) return;
      const boxes = g.nodes.map((n) => nodeBox(g, sizes, n.id)).filter((b) => b !== null);
      const minX = Math.min(...boxes.map((b) => b.x));
      const minY = Math.min(...boxes.map((b) => b.y));
      const maxX = Math.max(...boxes.map((b) => b.x + b.w));
      const maxY = Math.max(...boxes.map((b) => b.y + b.h));
      const padTop = 70;
      const padBottom = 80;
      const z = Math.min(
        1,
        (r.width - 60) / (maxX - minX + 40),
        (r.height - padTop - padBottom) / (maxY - minY + 40),
      );
      const zz = Math.max(0.3, Math.round(z * 100) / 100);
      setView({
        z: zz,
        x: Math.round((r.width - (maxX - minX) * zz) / 2 - minX * zz),
        y: Math.round(
          padTop + (r.height - padTop - padBottom - (maxY - minY) * zz) / 2 - minY * zz,
        ),
      });
    },
    [graph, sizes],
  );

  // 처음: 다 들어가면 100%(조건 위치 그대로), 넘치면 화면에 맞춤
  useEffect(() => {
    const g = pendingFit.current;
    if (!g) return;
    pendingFit.current = null;
    fit(g);
  });
  const fitted = useRef(false);
  useEffect(() => {
    if (fitted.current || Object.keys(sizes).length < graph.nodes.length) return;
    fitted.current = true;
    const r = canvasRef.current?.rect();
    if (!r) return;
    const maxX = Math.max(0, ...graph.nodes.map((n) => (n.x ?? 0) + (sizes[n.id]?.w ?? 150)));
    const maxY = Math.max(0, ...graph.nodes.map((n) => (n.y ?? 0) + (sizes[n.id]?.h ?? 64)));
    if (maxX + 20 > r.width || maxY + 80 > r.height) fit();
  }, [sizes, graph, fit]);

  const zoomBy = (f: number) => {
    const r = canvasRef.current?.rect();
    const px = (r?.width ?? 800) / 2;
    const py = (r?.height ?? 600) / 2;
    const z = Math.min(2, Math.max(0.3, Math.round(view.z * f * 10) / 10));
    setView({ z, x: px - ((px - view.x) / view.z) * z, y: py - ((py - view.y) / view.z) * z });
  };

  const centerOn = (id: string) => {
    const b = nodeBox(graph, sizes, id);
    const r = canvasRef.current?.rect();
    if (!b || !r) return;
    const sx = b.x * view.z + view.x;
    const sy = b.y * view.z + view.y;
    if (sx > 40 && sx + b.w * view.z < r.width - 40 && sy > 70 && sy + b.h * view.z < r.height - 80)
      return;
    setView({
      ...view,
      x: r.width / 2 - (b.x + b.w / 2) * view.z,
      y: r.height / 2 - (b.y + b.h / 2) * view.z,
    });
  };

  const goProblem = (p: Problem) => {
    setTip(t.problems.tip(kindNames[p.kind], p.short));
    window.setTimeout(() => {
      setTip(null);
    }, 5000);
    if (p.node) {
      setSel({ kind: 'node', id: p.node });
      setFocusField(p.field || null);
      setNextOpen(false);
      setProblemsOpen(false);
      centerOn(p.node);
    }
  };

  // ── 키보드 ───────────────────────────────────────────────────────────────
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const typing = el?.tagName === 'INPUT' || el?.tagName === 'TEXTAREA';
      const mod = e.ctrlKey || e.metaKey;
      if (mod && (e.key === 'z' || e.key === 'Z') && !typing) {
        e.preventDefault();
        setHist(e.shiftKey ? redo(hist) : undo(hist));
        return;
      }
      if (mod && (e.key === 'y' || e.key === 'Y') && !typing) {
        e.preventDefault();
        setHist(redo(hist));
        return;
      }
      if (e.key === 'Escape') {
        setSel(null);
        setConn(null);
        setAdding(null);
        setShowKeys(false);
        setShowMode(false);
        setNextOpen(false);
        return;
      }
      if (typing) return;
      const nid = el?.closest<HTMLElement>('[data-node]')?.dataset.node;
      if ((e.key === 'Delete' || e.key === 'Backspace') && sel) {
        e.preventDefault();
        removeSelected();
        return;
      }
      if (e.key === 'Enter' && nid) {
        e.preventDefault();
        if (sel?.kind === 'node' && sel.id === nid) setNextOpen(true);
        else select({ kind: 'node', id: nid });
      }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  });

  // ── 나가기 확인 ──────────────────────────────────────────────────────────
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      dirty && !leaving.current && currentLocation.pathname !== nextLocation.pathname,
  );
  useEffect(() => {
    if (!dirty) return;
    const before = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener('beforeunload', before);
    return () => {
      window.removeEventListener('beforeunload', before);
    };
  }, [dirty]);

  // ── 저장 ─────────────────────────────────────────────────────────────────
  const save = async () => {
    setSaving(true);
    setSaveError(null);
    const body: Body = { name: name || t.newTitle, graph };
    try {
      if (sid === null) {
        const r = await api.post<{ id: number; no: number; name: string }>('/api/strategies', {
          body,
        });
        leaving.current = true;
        void qc.invalidateQueries();
        void navigate(`/strategies/${String(r.id)}/edit`, {
          replace: true,
          state: { saved: r.no },
        });
        return;
      }
      const r = await api.post<{ no: number; name: string }>(
        `/api/strategies/${String(sid)}/versions`,
        { body },
      );
      setSaved({ name: r.name, graph });
      setSavedNo(r.no);
      setSid(sid);
      void qc.invalidateQueries();
      say({ text: t.saved(r.no), action: 'backtest' }, 8000);
    } catch (e) {
      setSaveError(isApiError(e) ? e.message : t.saveFailed);
    } finally {
      setSaving(false);
    }
  };

  // ── 화면 ─────────────────────────────────────────────────────────────────
  const tone = problemTone(analysis);
  const onlyHow = analysis.problems.length === 1 && analysis.problems[0]?.field === 'how';
  const statusTitle =
    tone === 'ok'
      ? !dirty && savedNo !== null
        ? t.status.savedTitle(savedNo)
        : t.status.okTitle
      : t.status.problemsTitle(analysis.problems.length, problemParts(analysis));
  const statusBody =
    tone === 'ok'
      ? !dirty && savedNo !== null
        ? t.status.savedBody
        : t.status.okBody
      : onlyHow
        ? t.status.howBody
        : t.status.body;
  const chip = isNew
    ? name
      ? t.chipNew
      : t.chipNewOnly
    : dirty
      ? t.chipFrom(savedNo ?? 1, (savedNo ?? 0) + 1)
      : t.chipSaved(savedNo ?? 1);
  const nextNo = isNew ? 1 : (savedNo ?? 0) + 1;
  const tags = nodeTags(cat, graph);
  const mode = analysis.mode;

  const nextOptions = (from: string): NextOption[] => {
    const a = node(from);
    if (!a) return [];
    const sa = stageOf(cat, a.piece);
    const allowed = new Set(catalog.next[sa]);
    const before = analysis;
    const out: NextOption[] = [];
    for (const b of graph.nodes) {
      if (b.id === from) continue;
      const why = edgeReason(cat, graph, from, b.id);
      const sb = stageOf(cat, b.piece);
      if (why === null) {
        const after = analyze(cat, addEdge(graph, from, b.id));
        const deadBefore = before.entry.findIndex(
          (p) => !p.complete && p.nodes[p.nodes.length - 1] === from,
        );
        const wasLoose = before.problems.some((p) => p.kind === 'loose' && p.node === b.id);
        const group = (x: SlotKey) =>
          x === 'signal' || x === 'filter' ? 'e' : x === 'sell' ? 's' : '';
        let line: string;
        if (
          deadBefore >= 0 &&
          (sb === 'select' || sb === 'buy') &&
          (after.counts.dead ?? 0) < (before.counts.dead ?? 0)
        )
          line = t.next.deadFixed(josa(t.paths.entryRow(deadBefore + 1), J.iga));
        else if (wasLoose) line = t.next.looseFixed;
        else if (group(sa) && group(sa) === group(sb))
          line = t.next.chain(
            slotCircle(cat, sa),
            josa(catalog.slots.find((x) => x.key === sb)?.name ?? '', J.eul),
          );
        else line = t.next.plain(slotCircle(cat, sa), josa(labelOf(cat, b), J.ro));
        out.push({ id: b.id, ok: true, line, order: STAGE_INDEX[sb] });
      } else if (allowed.has(sb) && why !== graphRules.dup && why !== graphRules.cycle) {
        out.push({ id: b.id, ok: false, line: why, order: STAGE_INDEX[sb] });
      }
    }
    return out.sort((x, y) => Number(y.ok) - Number(x.ok) || y.order - x.order);
  };

  const edgeEffects = (e: GraphEdge): string[] => {
    const after = analyze(cat, removeEdge(graph, e));
    const out: string[] = [];
    const w = pathsWith(e);
    for (const x of w.entry) out.push(t.edge.pathGone(josa(t.paths.entryRow(x.i + 1), J.iga)));
    for (const x of w.sell) out.push(t.edge.pathGone(josa(t.paths.sellRow(x.i + 1), J.iga)));
    const had = (k: string, id: string) =>
      analysis.problems.some((p) => p.kind === k && p.node === id);
    for (const p of after.problems) {
      const n = node(p.node);
      if (!n) continue;
      if (p.kind === 'dead' && !had('dead', p.node))
        out.push(t.edge.becomesDead(josa(labelOf(cat, n), J.eun)));
      if (p.kind === 'loose' && !had('loose', p.node))
        out.push(t.edge.becomesLoose(josa(labelOf(cat, n), J.eun)));
    }
    if (after.mode !== analysis.mode && after.mode !== null)
      out.push(t.edge.modeChange(josa(modeNames[after.mode], J.ro)));
    return [...new Set(out)];
  };

  const connectLines = (from: string): string[] => {
    const a = node(from);
    if (!a) return [];
    const sa = stageOf(cat, a.piece);
    const names = catalog.next[sa].map((s) => slotLabel(cat, s));
    const hasSelect = graph.nodes.some((n) => stageOf(cat, n.piece) === 'select');
    const list =
      hasSelect && (sa === 'signal' || sa === 'filter' || sa === 'universe')
        ? names.filter((x) => !x.startsWith('⑤'))
        : names;
    const out = [t.connect.after(slotLabel(cat, sa), josa(list.join(' · '), J.eul))];
    if (hasSelect && (sa === 'signal' || sa === 'filter' || sa === 'universe'))
      out.push(t.connect.selectOnly);
    return out;
  };

  let side: React.ReactNode;
  if (conn) {
    const bad = conn.over && !conn.ok.has(conn.over) && conn.why ? conn.why : null;
    const a = node(conn.from);
    const b = conn.over ? node(conn.over) : undefined;
    side = (
      <>
        <ConnectInfo
          lines={connectLines(conn.from)}
          bad={
            bad && a && b
              ? t.connect.bad(
                  slotLabel(cat, stageOf(cat, a.piece)),
                  josa(slotLabel(cat, stageOf(cat, b.piece)), J.ro),
                  t.connect.whyLong(bad),
                )
              : null
          }
        />
        <div className={styles.sideGap} />
        <PathsPanel cat={cat} graph={graph} analysis={analysis} />
      </>
    );
  } else if (drop?.ghost) {
    const near = drop.near;
    let title = '';
    let path = '';
    if (near) {
      const w = pathsWith(near);
      const first = w.entry[0] ?? w.sell[0];
      const label = w.entry[0]
        ? t.paths.entryRow(w.entry[0].i + 1)
        : w.sell[0]
          ? t.paths.sellRow(w.sell[0].i + 1)
          : '';
      if (first) {
        const nid = '__new__';
        const nodes = first.p.nodes.flatMap((id) => (id === near.from ? [id, nid] : [id]));
        const g2: Graph = {
          nodes: [
            ...graph.nodes,
            {
              id: nid,
              piece: drag?.piece ?? '',
              params: blankParams(catalog, drag?.piece ?? ''),
              x: 0,
              y: 0,
            },
          ],
          edges: graph.edges,
        };
        path = pathText(cat, g2, nodes);
        title = t.drop.previewTitle(josa(label, J.iga));
      }
    }
    side = (
      <>
        <DropInfo title={title} path={path} free={!near} />
        <div className={styles.sideGap} />
        <PathsPanel cat={cat} graph={graph} analysis={analysis} />
      </>
    );
  } else if (adding) {
    const { head, options } = addOptions(adding.piece);
    side = (
      <AddPanel
        cat={cat}
        piece={adding.piece}
        head={head}
        options={options}
        choice={adding.choice}
        onChoice={(k) => {
          setAdding({ ...adding, choice: k });
        }}
        onAdd={doAdd}
      />
    );
  } else if (selNode) {
    side = (
      <NodePanel
        key={selNode.id}
        cat={cat}
        catalog={catalog}
        graph={graph}
        analysis={analysis}
        node={selNode}
        focusField={focusField}
        nextOpen={nextOpen}
        next={nextOpen ? nextOptions(selNode.id) : []}
        onParam={(k, v: ParamValue) => {
          commit(setParam(graph, selNode.id, k, v), `p:${selNode.id}:${k}`);
        }}
        onNext={() => {
          setNextOpen(!nextOpen);
        }}
        onPickNext={(to) => {
          connect(selNode.id, to);
          setNextOpen(false);
        }}
        onRemove={removeSelected}
      />
    );
  } else if (sel?.kind === 'edge') {
    side = (
      <EdgePanel
        cat={cat}
        graph={graph}
        analysis={analysis}
        edge={sel.edge}
        effects={edgeEffects(sel.edge)}
        onRemove={removeSelected}
      />
    );
  } else {
    side = (
      <PathsSide
        cat={cat}
        graph={graph}
        analysis={analysis}
        hot={hot?.key ?? null}
        onHover={(key, nodes) => {
          setHot(key && nodes ? { key, nodes: new Set(nodes) } : null);
        }}
        problemsOpen={problemsOpen}
        onCloseProblems={() => {
          setProblemsOpen(false);
        }}
        onGo={goProblem}
        note={middleNote && hist.past.length > 0 ? t.node.middleNote : null}
      />
    );
  }

  const connTip =
    conn?.over && conn.ok.has(conn.over)
      ? (() => {
          const a = node(conn.from);
          const b = node(conn.over);
          return a && b ? t.connect.okTip(labelOf(cat, a), josa(labelOf(cat, b), J.ro)) : null;
        })()
      : null;
  const dropTip = drop?.near
    ? (() => {
        const a = node(drop.near.from);
        const b = node(drop.near.to);
        return a && b ? t.drop.tip(josa(labelOf(cat, a), J.gwa), labelOf(cat, b)) : null;
      })()
    : null;
  const topTip = connTip ?? dropTip ?? tip;
  const backTo = isNew ? '/strategies' : `/strategies/${String(sid)}`;

  return (
    <div className={styles.editor}>
      <div className={styles.topBar}>
        <div className="stack-tight">
          <BackLink to={backTo}>{isNew ? t.back : name}</BackLink>
          <div className={styles.titleRow}>
            <h1 className="t-title">{t.title(name || t.newTitle)}</h1>
            <span className={clsx('t-label', styles.verChip)}>
              <Pencil size={14} aria-hidden />
              {chip}
            </span>
          </div>
        </div>
        <div className={styles.topRight}>
          <button
            type="button"
            className={clsx(styles.status, styles[`status-${tone}`])}
            aria-expanded={problemsOpen}
            disabled={tone === 'ok'}
            onClick={() => {
              select(null);
              setProblemsOpen(!problemsOpen);
            }}
          >
            {tone === 'ok' ? (
              <CircleCheck size={18} className="c-success" aria-hidden />
            ) : tone === 'warn' ? (
              <TriangleAlert size={18} className="c-warn" aria-hidden />
            ) : (
              <CircleX size={18} className="c-error" aria-hidden />
            )}
            <span className={styles.statusText}>
              <span className="t-label">{statusTitle}</span>
              <span className="t-caption">{statusBody}</span>
            </span>
            {tone === 'ok' ? null : <ChevronDown size={18} className="c-muted" aria-hidden />}
          </button>
          <Button
            kind="primary"
            disabled={!dirty || saving}
            onClick={() => void save()}
            className={styles.saveButton}
          >
            {saving ? t.saving : dirty ? t.save(nextNo) : t.nothingToSave}
          </Button>
        </div>
      </div>
      {saveError ? (
        <p className={clsx('t-caption c-error', styles.saveError)}>{saveError}</p>
      ) : null}
      <div className={styles.work}>
        <Palette
          catalog={catalog}
          cat={cat}
          graph={graph}
          dragging={drag?.active ? drag.piece : null}
          picked={adding?.piece ?? null}
          onPointerDown={onPalDown}
          onPick={(piece) => {
            const around = sel?.kind === 'node' ? sel.id : null;
            const { options } = addOptions(piece, around);
            setAdding({ piece, choice: options[0]?.key ?? 'free', around });
          }}
        />
        <div className={styles.canvasWrap}>
          <Canvas
            ref={canvasRef}
            cat={cat}
            graph={graph}
            analysis={analysis}
            sizes={sizes}
            onSizes={setSizes}
            view={view}
            onView={setView}
            sel={sel}
            hot={hot?.nodes ?? null}
            tags={tags}
            conn={conn}
            drop={drop ?? addDrop}
            onSelect={select}
            onMove={(id, x, y) => {
              commit(moveNode(graph, id, x, y));
            }}
            onConnectStart={startConnect}
            onConnectMove={moveConnect}
            onConnectEnd={endConnect}
            onRemoveEdge={(e) => {
              commit(removeEdge(graph, e), null, t.toast.edgeRemoved);
              setSel(null);
            }}
            onKey={() => undefined}
            editable
          />
          {graph.nodes.length <= 4 &&
          graph.edges.length <= 3 &&
          isNew &&
          !drop?.ghost &&
          !sel &&
          !adding ? (
            <div className={styles.emptyHint}>
              <MousePointer2 size={18} className="c-muted" aria-hidden />
              <p className="t-body-strong">{t.empty.title}</p>
              <p className="t-caption c-muted">{t.empty.body}</p>
            </div>
          ) : null}
          <div className={styles.overTop}>
            <button
              type="button"
              className={clsx('t-caption', styles.modeChip, mode === null && styles.modeBlank)}
              aria-expanded={showMode}
              onClick={() => {
                setShowMode(!showMode);
              }}
            >
              <span>{t.mode.label}</span>
              <span className="t-label">{mode === null ? t.mode.blank : modeNames[mode]}</span>
              <Info size={14} aria-hidden />
            </button>
            <p className={clsx('t-caption', styles.readHow)}>
              <Workflow size={16} aria-hidden />
              {t.readHow}
            </p>
          </div>
          {showMode ? (
            <div className={styles.modePop} role="dialog" aria-label={t.mode.explainTitle}>
              <p className="t-body-strong">{t.mode.explainTitle}</p>
              {t.mode.explain.map((x) => (
                <p key={x} className="t-caption">
                  {x}
                </p>
              ))}
            </div>
          ) : null}
          {topTip ? <p className={clsx('t-caption', styles.tip)}>{topTip}</p> : null}
          {toast ? (
            <div className={styles.toast} role="status">
              <span className="t-body">{toast.text}</span>
              {toast.action === 'undo' ? (
                <button
                  type="button"
                  className="t-label"
                  onClick={() => {
                    setHist(undo(hist));
                    say(null);
                  }}
                >
                  {t.toast.undo}
                </button>
              ) : toast.action === 'backtest' && sid !== null ? (
                <button
                  type="button"
                  className="t-label"
                  onClick={() => void navigate(`/strategies/${String(sid)}/backtest`)}
                >
                  {t.toBacktest}
                </button>
              ) : null}
            </div>
          ) : null}
          <div className={styles.toolbar} role="toolbar" aria-label={t.tool.canvas}>
            <button
              type="button"
              className={clsx('t-label', styles.tool)}
              onClick={() => {
                const pos = autoLayout(cat, graph, sizes);
                const next = placeAll(graph, pos);
                commit(next, null, t.toast.layout);
                window.setTimeout(() => {
                  fit(next);
                }, 30);
              }}
            >
              <Workflow size={16} aria-hidden />
              {t.tool.layout}
            </button>
            <span className={styles.toolSep} />
            <button
              type="button"
              className={styles.tool}
              aria-label={t.tool.undo}
              disabled={hist.past.length === 0}
              onClick={() => {
                setHist(undo(hist));
              }}
            >
              <Undo2 size={18} aria-hidden />
            </button>
            <button
              type="button"
              className={styles.tool}
              aria-label={t.tool.redo}
              disabled={hist.future.length === 0}
              onClick={() => {
                setHist(redo(hist));
              }}
            >
              <Redo2 size={18} aria-hidden />
            </button>
            <span className={styles.toolSep} />
            <button
              type="button"
              className={styles.tool}
              aria-label={t.tool.zoomOut}
              onClick={() => {
                zoomBy(1 / 1.1);
              }}
            >
              <Minus size={18} aria-hidden />
            </button>
            <span className={clsx('t-label', styles.zoomText)}>
              {t.tool.zoom(Math.round(view.z * 100))}
            </span>
            <button
              type="button"
              className={styles.tool}
              aria-label={t.tool.zoomIn}
              onClick={() => {
                zoomBy(1.1);
              }}
            >
              <Plus size={18} aria-hidden />
            </button>
            <span className={styles.toolSep} />
            <button
              type="button"
              className={clsx('t-label', styles.tool)}
              onClick={() => {
                fit();
              }}
            >
              <Scan size={16} aria-hidden />
              {t.tool.fit}
            </button>
            <span className={styles.toolSep} />
            <button
              type="button"
              className={styles.tool}
              aria-label={t.tool.keys}
              aria-expanded={showKeys}
              onClick={() => {
                setShowKeys(!showKeys);
              }}
            >
              <CircleHelp size={18} aria-hidden />
            </button>
          </div>
          {drop?.ghost ? (
            <p className={clsx('t-caption', styles.legend)}>
              <span className={styles.legendDash} />
              {t.tool.dropLegend}
            </p>
          ) : null}
          {showKeys ? (
            <div className={styles.keysPop} role="dialog" aria-label={t.keys.title}>
              <p className="t-body-strong">{t.keys.title}</p>
              {t.keys.rows.map(([k, v]) => (
                <div key={k} className={styles.keyRow}>
                  <kbd className="t-label">{k}</kbd>
                  <span className="t-caption">{v}</span>
                </div>
              ))}
              <p className="t-caption c-muted">{t.keys.mac}</p>
            </div>
          ) : null}
        </div>
        <aside className={styles.side}>{side}</aside>
      </div>
      {drag?.active && !drop?.ghost ? (
        <div
          className={clsx('t-caption', styles.dragFloat)}
          style={{ left: drag.cx + 8, top: drag.cy + 8 }}
          aria-hidden
        >
          {catalog.pieces[drag.piece]?.name}
        </div>
      ) : null}
      {blocker.state === 'blocked' ? (
        <Sheet
          title={t.leave.title}
          onClose={() => {
            blocker.reset();
          }}
        >
          <p className="t-body">
            {isNew
              ? t.leave.bodyNew
              : t.leave.body(
                  [
                    ch.added ? t.leave.added(ch.added) : '',
                    ch.removed ? t.leave.removed(ch.removed) : '',
                    ch.lines ? t.leave.lines(ch.lines) : '',
                    ch.values ? t.leave.values(ch.values) : '',
                    ch.moved ? t.leave.moved(ch.moved) : '',
                  ]
                    .filter(Boolean)
                    .join(' · '),
                  savedNo ?? 1,
                )}
          </p>
          <div className="buttons">
            <Button
              kind="default"
              onClick={() => {
                blocker.reset();
              }}
            >
              {t.leave.stay}
            </Button>
            <Button
              kind="danger"
              onClick={() => {
                blocker.proceed();
              }}
            >
              {t.leave.go}
            </Button>
          </div>
        </Sheet>
      ) : null}
    </div>
  );
}
