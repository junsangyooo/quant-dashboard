// 좁은 창 편집 · 보기만(폭 1024 미만): 위 → 아래 그래프와 경로 목록. 편집은 창을 넓혀서 한다.
import clsx from 'clsx';
import { useMemo, useRef } from 'react';
import { Monitor, Scan } from 'lucide-react';
import type { Catalog } from '../../api/mvp';
import { Box } from '../../components/Box';
import { Card } from '../../components/Card';
import { GraphView } from '../../components/graph/GraphView';
import { PathsPanel } from '../../components/graph/PathsPanel';
import { StatusTag } from '../../components/Tags';
import { editorCopy as t } from '../../copy/editor';
import { modeNames } from '../../copy/graph';
import { analyze } from '../../graph/rules';
import { BackLink, Page } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';
import type { EditorStart } from './CanvasEditor';
import { withPositions } from './CanvasEditor';
import { ruleCatalog } from './model';
import styles from './Editor.module.css';

export function NarrowView({ catalog, start }: { catalog: Catalog; start: EditorStart }) {
  const cat = useMemo(() => ruleCatalog(catalog), [catalog]);
  const graph = useMemo(() => withPositions(cat, start.body.graph), [cat, start.body.graph]);
  const analysis = useMemo(() => analyze(cat, graph), [cat, graph]);
  const name = start.body.name || t.newTitle;
  const graphRef = useRef<HTMLDivElement>(null);
  useDocumentTitle(name);
  return (
    <Page width="narrow">
      <BackLink to={start.sid === null ? '/strategies' : `/strategies/${String(start.sid)}`}>
        {start.sid === null ? t.back : name}
      </BackLink>
      <h1 className="t-title">{name}</h1>
      <div className={styles.narrowTags}>
        <StatusTag kind="edit">
          {start.no === null ? t.chipViewOnlyNew : t.chipViewOnly(start.no)}
        </StatusTag>
        {analysis.mode ? <StatusTag kind="plain">{modeNames[analysis.mode]}</StatusTag> : null}
      </div>
      <Box tone="info" icon="none" title={undefined}>
        <span className={clsx('t-body-strong', styles.effectTitle)}>
          <Monitor size={18} aria-hidden />
          {t.narrow.title}
        </span>
        <span>{t.narrow.body}</span>
      </Box>
      <Card>
        <div ref={graphRef} className={styles.graphHead}>
          <h2 className="t-heading-1">{t.narrow.count(graph.nodes.length)}</h2>
          <button
            type="button"
            className={clsx('t-caption', styles.fitLink)}
            onClick={() => {
              graphRef.current?.scrollIntoView({ block: 'start' });
            }}
          >
            <Scan size={14} aria-hidden />
            {t.tool.fit}
          </button>
        </div>
        <GraphView cat={cat} graph={graph} analysis={analysis} label={name} />
        <p className="t-caption c-muted">{t.readHow}</p>
      </Card>
      <Card tone="outline">
        <PathsPanel cat={cat} graph={graph} analysis={analysis} />
      </Card>
    </Page>
  );
}
