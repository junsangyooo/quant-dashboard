// 캔버스 위 단계 하나(그림 V2-23): 머리(단계 이름 + 토글) · 조건 줄 · '+ 조건 추가' · 연결점.
import clsx from 'clsx';
import { Clock, Info, LineChart, Plus } from 'lucide-react';
import type { PointerEvent as ReactPointerEvent } from 'react';
import type { Block, Catalog, CatalogItem, ExecChip, Problem, Row } from '../../api/v2';
import { blockEditor as t } from '../../copy/blockEditor';
import { TOGGLE } from './model';
import { StageGlyph } from './StageGlyph';
import styles from './BlockEditor.module.css';

export interface BlockCardProps {
  block: Block;
  catalog: Catalog;
  chips: (ExecChip | null)[];
  problems: Problem[];
  selected: boolean;
  selectedRow: number | null;
  onSelectRow: (row: number) => void;
  onChangeRow: (row: number, next: Row) => void;
  onMatch: (match: Block['match']) => void;
  onAdd: () => void;
  onDragStart: (e: ReactPointerEvent) => void;
  onPortStart: (e: ReactPointerEvent) => void;
  onPortEnd: () => void;
}

const num = (v: unknown): number | null => (typeof v === 'number' ? v : null);

function NumberBox({
  value,
  onChange,
  label,
}: {
  value: number | null;
  onChange: (v: number | null) => void;
  label: string;
}) {
  return (
    <input
      className={styles.num}
      inputMode="decimal"
      aria-label={label}
      value={value ?? ''}
      onChange={(e) => {
        const raw = e.target.value.replace(/,/g, '').trim();
        if (raw === '') onChange(null);
        else if (!Number.isNaN(Number(raw))) onChange(Number(raw));
      }}
    />
  );
}

function OpSelect({
  item,
  row,
  catalog,
  onChange,
}: {
  item: CatalogItem;
  row: Row;
  catalog: Catalog;
  onChange: (op: string) => void;
}) {
  if (item.ops.length < 2) return null;
  return (
    <select
      className={styles.select}
      aria-label={item.short}
      value={row.op}
      onChange={(e) => {
        onChange(e.target.value);
      }}
    >
      {item.ops.map((o) => (
        <option key={o} value={o}>
          {catalog.ops[o]}
        </option>
      ))}
    </select>
  );
}

export function RowLine({
  row,
  catalog,
  chip,
  onChange,
}: {
  row: Row;
  catalog: Catalog;
  chip: ExecChip | null;
  onChange: (next: Row) => void;
}) {
  const item = catalog.items.find((i) => i.id === row.item);
  if (!item) return null;
  const setValue = (v: number | null) => {
    onChange({ ...row, value: v });
  };
  const setParam = (k: string, v: number | string | null) => {
    onChange({ ...row, params: { ...row.params, [k]: v } });
  };
  const unit = item.value?.unit ?? '';
  const parts = [];
  if (item.id === 'stop_loss' || item.id === 'trailing_stop' || item.id === 'take_profit') {
    parts.push(
      <span key="n" className={styles.chip}>
        {item.short}
      </span>,
      <span key="s">{item.id === 'take_profit' ? '+' : '−'}</span>,
      <NumberBox key="v" value={num(row.value)} onChange={setValue} label={item.short} />,
      <span key="u" className={styles.unit}>
        {unit}
      </span>,
    );
  } else if (item.id === 'top_n') {
    const by = String(row.params.by ?? 'strength');
    const byItem = catalog.items.find((i) => i.id === by);
    parts.push(
      <span key="by" className={styles.chip}>
        {by === 'strength' ? t.sortStrength : (byItem?.short ?? by)}
      </span>,
      <select
        key="o"
        className={styles.select}
        aria-label={t.sortOrderLabel}
        value={String(row.params.order ?? 'desc')}
        onChange={(e) => {
          setParam('order', e.target.value);
        }}
      >
        <option value="desc">{t.sortDesc}</option>
        <option value="asc">{t.sortAsc}</option>
      </select>,
      <strong key="t">{t.top}</strong>,
      <NumberBox key="v" value={num(row.value)} onChange={setValue} label={item.short} />,
      <span key="u" className={styles.unit}>
        {unit}
      </span>,
    );
  } else if (item.id === 'next_open') {
    parts.push(
      <span key="a" className={styles.chip}>
        {t.nextOpen}
      </span>,
      <span key="b" className={styles.chip}>
        {t.cooldown}
      </span>,
      <NumberBox key="v" value={num(row.value)} onChange={setValue} label={t.cooldown} />,
      <span key="u" className={styles.unit}>
        {unit}
      </span>,
    );
  } else if (
    item.id === 'equal' ||
    item.id === 'exclude_preferred' ||
    item.id === 'exclude_leveraged' ||
    item.id === 'exclude_warning'
  ) {
    parts.push(
      <span key="a" className={styles.chip}>
        {item.short}
      </span>,
    );
  } else {
    parts.push(
      <span key="n" className={styles.chip}>
        {item.short}
      </span>,
    );
    for (const p of item.params) {
      if (!(p.key in row.params)) continue;
      if (p.choices.length) {
        parts.push(
          <select
            key={p.key}
            className={styles.select}
            aria-label={p.label}
            value={String(row.params[p.key] ?? '')}
            onChange={(e) => {
              setParam(p.key, e.target.value || null);
            }}
          >
            <option value="" />
            {p.choices.map((c) => (
              <option key={c} value={c}>
                {c in t.choice ? t.choice[c as keyof typeof t.choice] : c}
              </option>
            ))}
          </select>,
        );
      } else {
        parts.push(
          <NumberBox
            key={p.key}
            value={num(row.params[p.key])}
            onChange={(v) => {
              setParam(p.key, v);
            }}
            label={p.label}
          />,
          <span key={`${p.key}u`} className={styles.unit}>
            {t.dayUnit}
          </span>,
        );
      }
    }
    if (item.choices.length) {
      const picked = Array.isArray(row.value) ? row.value : [];
      parts.push(
        <span key="c" className={styles.chip}>
          {picked.length
            ? picked
                .map((c) => (c in t.choice ? t.choice[c as keyof typeof t.choice] : c))
                .join(' · ')
            : t.blank}
        </span>,
      );
    } else if (item.id === 'manual_list') {
      const picked = Array.isArray(row.value) ? row.value : [];
      parts.push(
        <span key="c" className={styles.num}>
          {picked.length || ''}
        </span>,
        <span key="u" className={styles.unit}>
          {unit}
        </span>,
      );
    } else {
      parts.push(
        <OpSelect
          key="op"
          item={item}
          row={row}
          catalog={catalog}
          onChange={(op) => {
            onChange({ ...row, op });
          }}
        />,
      );
      if (
        ![
          'cross_up',
          'cross_down',
          'above',
          'below',
          'aligned_up',
          'aligned_down',
          'pick',
          'exclude',
        ].includes(row.op)
      ) {
        parts.push(
          <NumberBox key="v" value={num(row.value)} onChange={setValue} label={item.short} />,
          <span key="u" className={styles.unit}>
            {unit}
          </span>,
        );
      }
    }
  }
  return (
    <>
      {parts}
      {chip ? (
        <span className={styles.execChip}>
          {chip.exec === 'close' ? (
            <Clock size={14} aria-hidden />
          ) : (
            <LineChart size={14} aria-hidden />
          )}
          {chip.reason ? `${chip.name} · ${chip.reason}` : chip.name}
        </span>
      ) : null}
      {item.chips
        .filter((c) => c !== t.yesterdayChip)
        .map((c) => (
          <span key={c} className={styles.tailChip}>
            <Info size={12} aria-hidden />
            {c.split(' · ')[0]}
          </span>
        ))}
    </>
  );
}

export function BlockCard({
  block,
  catalog,
  chips,
  problems,
  selected,
  selectedRow,
  onSelectRow,
  onChangeRow,
  onMatch,
  onAdd,
  onDragStart,
  onPortStart,
  onPortEnd,
}: BlockCardProps) {
  const stage = catalog.stages.find((s) => s.id === block.stage);
  const bad = problems.some((p) => p.block === block.id && p.kind !== 'blank');
  return (
    <div
      className={clsx(
        styles.block,
        selected && styles.blockSelected,
        bad && !selected && styles.blockProblem,
      )}
      style={{ left: block.x, top: block.y }}
      data-block={block.id}
    >
      {block.stage !== 'universe' && block.stage !== 'weight' ? (
        <button
          type="button"
          className={clsx(styles.port, styles.portIn)}
          aria-label={t.portIn}
          onPointerUp={onPortEnd}
        />
      ) : null}
      <button
        type="button"
        className={clsx(styles.port, styles.portOut)}
        aria-label={t.portOut}
        onPointerDown={onPortStart}
      />
      <div
        className={styles.blockHead}
        style={{ background: `var(--stage-${block.stage})` }}
        onPointerDown={onDragStart}
      >
        <span className={styles.blockName} style={{ color: `var(--stage-${block.stage}-ink)` }}>
          <StageGlyph stage={block.stage} />
          {stage ? `${stage.circle} ${stage.name}` : block.stage}
        </span>
        {TOGGLE.includes(block.stage) ? (
          <select
            className={styles.toggle}
            aria-label={t.toggleLabel}
            value={block.match}
            onPointerDown={(e) => {
              e.stopPropagation();
            }}
            onChange={(e) => {
              onMatch(e.target.value as Block['match']);
            }}
          >
            <option value="all">{t.match.all}</option>
            <option value="any">{t.match.any}</option>
          </select>
        ) : null}
      </div>
      <div className={styles.rows}>
        {block.rows.map((row, i) => (
          <div
            key={i}
            className={clsx(
              styles.row,
              selectedRow === i && styles.rowSelected,
              problems.some((p) => p.block === block.id && p.row === i && p.kind !== 'blank') &&
                styles.rowProblem,
            )}
            onClick={() => {
              onSelectRow(i);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onSelectRow(i);
            }}
            role="button"
            tabIndex={0}
          >
            <RowLine
              row={row}
              catalog={catalog}
              chip={chips[i] ?? null}
              onChange={(next) => {
                onChangeRow(i, next);
              }}
            />
          </div>
        ))}
      </div>
      {block.stage !== 'buy' ? (
        <button type="button" className={styles.add} onClick={onAdd}>
          <Plus size={14} aria-hidden />
          {t.addRow}
        </button>
      ) : null}
    </div>
  );
}
