// '표로 보기': the same values as a chart, as a table (accessibility alternative).
import clsx from 'clsx';
import type { ReactNode } from 'react';
import styles from './charts.module.css';

export interface ChartTableProps {
  caption: ReactNode;
  columns: readonly string[];
  rows: readonly (readonly ReactNode[])[];
  id?: string | undefined;
  className?: string | undefined;
}

export function ChartTable({ caption, columns, rows, id, className }: ChartTableProps) {
  return (
    <table id={id} className={clsx(styles.table, 't-caption', className)}>
      <caption className="t-label">{caption}</caption>
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c} scope="col">
              {c}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            {r.map((cell, j) =>
              j === 0 ? (
                <th key={j} scope="row">
                  {cell}
                </th>
              ) : (
                <td key={j}>{cell}</td>
              ),
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
