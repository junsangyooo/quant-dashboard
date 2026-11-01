// 왼쪽 조건 목록 15개: 단계별, 검색, 끌어 오기 · 눌러서 추가, 하나만 놓는 조건은 잠김.
import clsx from 'clsx';
import { useState, type PointerEvent as ReactPointerEvent } from 'react';
import { GripVertical, Lock, Search } from 'lucide-react';
import type { Catalog, Graph } from '../../api/mvp';
import { StageIcon } from '../../components/StageIcon';
import { editorCopy as t } from '../../copy/editor';
import { addReason, type RuleCatalog } from '../../graph/rules';
import styles from './Editor.module.css';

export function Palette({
  catalog,
  cat,
  graph,
  dragging,
  picked,
  onPointerDown,
  onPick,
}: {
  catalog: Catalog;
  cat: RuleCatalog;
  graph: Graph;
  dragging: string | null;
  picked: string | null;
  onPointerDown: (piece: string, e: ReactPointerEvent<HTMLButtonElement>) => void;
  onPick: (piece: string) => void;
}) {
  const [q, setQ] = useState('');
  const pieces = Object.values(catalog.pieces);
  const query = q.trim();
  const shown = pieces.filter((p) => !query || p.name.includes(query));
  return (
    <aside className={styles.palette} aria-label={t.palette.title(pieces.length)}>
      <div className="stack-tight">
        <h2 className="t-body-strong">{t.palette.title(pieces.length)}</h2>
        <p className="t-caption c-muted">{t.palette.lead}</p>
      </div>
      <label className={styles.search}>
        <Search size={16} className="c-muted" aria-hidden />
        <input
          className="t-body"
          value={q}
          placeholder={t.palette.search}
          aria-label={t.palette.search}
          onChange={(e) => {
            setQ(e.target.value);
          }}
        />
      </label>
      {shown.length === 0 ? <p className="t-caption c-muted">{t.palette.none}</p> : null}
      {catalog.slots.map((slot) => {
        const list = shown.filter((p) => p.slot === slot.key);
        if (list.length === 0) return null;
        return (
          <div key={slot.key} className={styles.palGroup}>
            <p className={clsx('t-caption', styles.palHead)}>
              <StageIcon slot={slot.key} size={14} />
              {slot.label}
            </p>
            {list.map((p) => {
              const why = addReason(cat, graph, p.id);
              const count = graph.nodes.filter((n) => n.piece === p.id).length;
              const locked = why !== null;
              return (
                <button
                  key={p.id}
                  type="button"
                  className={clsx(
                    't-caption',
                    styles.palItem,
                    locked && styles.palLocked,
                    dragging === p.id && styles.palMoving,
                    picked === p.id && styles.palPicked,
                  )}
                  aria-disabled={locked}
                  title={why ?? undefined}
                  onPointerDown={(e) => {
                    if (!locked) onPointerDown(p.id, e);
                  }}
                  onKeyDown={(e) => {
                    if ((e.key === 'Enter' || e.key === ' ') && !locked) {
                      e.preventDefault();
                      onPick(p.id);
                    }
                  }}
                >
                  {locked ? (
                    <Lock size={14} className="c-muted" aria-hidden />
                  ) : (
                    <GripVertical size={14} className="c-muted" aria-hidden />
                  )}
                  <span className={styles.palName}>{p.name}</span>
                  {dragging === p.id ? (
                    <span className={clsx('t-label', 'c-accent')}>{t.palette.moving}</span>
                  ) : locked ? (
                    <span className={clsx('t-micro', styles.palMeta)}>{t.palette.once}</span>
                  ) : count > 0 ? (
                    <span className={clsx('t-caption', styles.palMeta)}>
                      {t.palette.placed(count)}
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        );
      })}
    </aside>
  );
}
