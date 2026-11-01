// 12 예시 전략 상세(보기만): 숫자는 예시 · 백테스트(결과는 남지 않음) · 이 예시로 새 전략. 넓으면 그래프 | 경로.
import { useNavigate, useParams } from 'react-router';
import { useCatalog, useExample } from '../../api/mvp';
import { Box } from '../../components/Box';
import { Button } from '../../components/Buttons';
import { Card } from '../../components/Card';
import { GraphView } from '../../components/graph/GraphView';
import { PathsPanel } from '../../components/graph/PathsPanel';
import { StatusTag } from '../../components/Tags';
import { strategyCopy } from '../../copy/strategy';
import { BackLink, Page, Split } from '../../shell/Layout';
import { useDocumentTitle } from '../../shell/page';
import { ruleCatalog } from '../Editor/model';
import { LoadError } from '../LoadError';
import { ExampleChip } from '../Start/StartParts';
import styles from './Strategies.module.css';

const t = strategyCopy.example;

export function ExampleScreen() {
  const eid = useParams().eid ?? '';
  const q = useExample(eid);
  const catalog = useCatalog().data;
  const navigate = useNavigate();
  useDocumentTitle(q.data?.name ?? strategyCopy.title);
  if (q.isError) return <LoadError onRetry={() => void q.refetch()} />;
  const ex = q.data;
  if (!ex || !catalog) return null;
  const cat = ruleCatalog(catalog);
  const a = ex.analysis;
  return (
    <Page width="split">
      <Split
        main={
          <>
            <BackLink to="/strategies">{t.back}</BackLink>
            <h1 className={`t-title ${styles.exTitle}`}>
              <ExampleChip />
              {ex.name}
            </h1>
            <div className={styles.tags}>
              <StatusTag kind="plain">{ex.summary.mode_name}</StatusTag>
            </div>
            <Box tone="info" title={t.noteTitle}>
              {t.noteBody}
            </Box>
            <div className="buttons">
              <Button kind="primary" onClick={() => void navigate(`/examples/${eid}/backtest`)}>
                {t.backtest}
              </Button>
              <Button
                kind="default"
                onClick={() => void navigate(`/strategies/new?start=example&example=${eid}`)}
              >
                {t.copy}
              </Button>
            </div>
            <Card>
              <h2 className="t-heading-1">{t.graphTitle(ex.summary.nodes)}</h2>
              <p className="t-caption c-muted">{t.graphLine(a.entry.length, a.sell.length)}</p>
              <GraphView cat={cat} graph={ex.body.graph} analysis={a} label={ex.name} />
              <p className="t-caption c-muted">{strategyCopy.detail.readHow}</p>
            </Card>
          </>
        }
        side={
          <Card tone="outline">
            <PathsPanel cat={cat} graph={ex.body.graph} analysis={a} />
          </Card>
        }
      />
    </Page>
  );
}
