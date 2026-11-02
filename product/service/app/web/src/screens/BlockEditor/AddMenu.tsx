// '+ 조건 추가' 메뉴(그림 V2-23 조건 추가 메뉴 · 분류 / 검색 / 잠긴 분류): 검색 칸 + 이 단계에 들어갈 분류.
import clsx from 'clsx';
import { ChevronDown, ChevronRight, Lock, Search } from 'lucide-react';
import { useState } from 'react';
import type { Block, Catalog, CatalogItem } from '../../api/v2';
import { blockEditor as t } from '../../copy/blockEditor';
import styles from './BlockEditor.module.css';

export interface AddMenuProps {
  block: Block;
  catalog: Catalog;
  x: number;
  y: number;
  onPick: (item: CatalogItem) => void;
  onClose: () => void;
}

function meta(item: CatalogItem): string {
  const unit = item.value?.unit ?? '';
  const bt = item.backtest === 'yes' ? '' : t.backtestMeta[item.backtest];
  return [unit, bt].filter(Boolean).join(' · ');
}

const ORDER = [...t.categoryOrder] as string[];

export function AddMenu({ block, catalog, x, y, onPick, onClose }: AddMenuProps) {
  const [q, setQ] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const stage = catalog.stages.find((s) => s.id === block.stage);
  const items = catalog.items.filter((i) => i.stages.includes(block.stage));
  const has = new Set(block.rows.map((r) => r.item));
  const found = q.trim()
    ? items.filter((i) => i.name.includes(q.trim()) || i.short.includes(q.trim()))
    : [];
  const cats = [...catalog.categories]
    .sort((a, b) => ORDER.indexOf(a) - ORDER.indexOf(b))
    .filter((c) => items.some((i) => i.category === c));

  const itemButton = (i: CatalogItem) => {
    const locked = i.lock === 'dart' && !catalog.dart;
    const already = has.has(i.id);
    return (
      <button
        key={i.id}
        type="button"
        className={clsx(styles.itemButton, 't-caption')}
        disabled={locked || already}
        onClick={() => {
          onPick(i);
        }}
      >
        <span>{i.name}</span>
        <span className={styles.muted}>{already ? t.already : meta(i)}</span>
      </button>
    );
  };

  return (
    <div className={styles.popover} style={{ left: x, top: y }} role="dialog" aria-label={t.addRow}>
      <label className={styles.fieldRow}>
        <Search size={16} aria-hidden />
        <input
          className={styles.search}
          placeholder={t.searchPlaceholder}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Escape') onClose();
          }}
        />
      </label>
      <p className={clsx(styles.muted, 't-caption')}>
        {stage ? t.menuLead(stage.circle, stage.name) : ''}
      </p>
      {q.trim() ? (
        found.length ? (
          found.map(itemButton)
        ) : (
          <p className={styles.muted}>{t.noResult}</p>
        )
      ) : (
        cats.map((c) => {
          const inCat = items.filter((i) => i.category === c);
          const locked = inCat.every((i) => i.lock === 'dart') && !catalog.dart;
          const isOpen = open === c;
          return (
            <div key={c}>
              <button
                type="button"
                className={clsx(styles.category, isOpen && styles.categoryOpen)}
                aria-expanded={isOpen}
                onClick={() => {
                  setOpen(isOpen ? null : c);
                }}
              >
                <span>
                  {locked ? <Lock size={14} aria-hidden /> : null} {c}
                </span>
                <span className={styles.muted}>
                  {String(inCat.length)}{' '}
                  {isOpen ? (
                    <ChevronDown size={14} aria-hidden />
                  ) : (
                    <ChevronRight size={14} aria-hidden />
                  )}
                </span>
              </button>
              {isOpen && locked ? (
                <p className={clsx(styles.muted, 't-caption')}>{t.menuLocked}</p>
              ) : null}
              {isOpen ? inCat.map(itemButton) : null}
            </div>
          );
        })
      )}
    </div>
  );
}
