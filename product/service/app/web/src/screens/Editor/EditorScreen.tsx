// 전략 편집 화면: 저장된 전략(/strategies/:id/edit) 또는 아직 저장하지 않은 새 전략(/strategies/new?start=blank|example).
// 폭 1024 이상은 캔버스 편집, 그보다 좁으면 보기만(화면에 맞춘 위 → 아래 그래프 + 경로).
import { useLocation, useParams, useSearchParams } from 'react-router';
import { useCatalog, useExample, useStrategy, type Body } from '../../api/mvp';
import { editorCopy as t } from '../../copy/editor';
import { useMediaQuery } from '../../lib/useMedia';
import { LoadError } from '../LoadError';
import { CanvasEditor, type EditorStart } from './CanvasEditor';
import { NarrowView } from './NarrowView';

export const EDIT_MIN = '(min-width: 1024px)';

export function EditorScreen() {
  const params = useParams();
  const [search] = useSearchParams();
  const location = useLocation();
  const isNew = params.id === undefined;
  const sid = Number(params.id ?? 0);
  const fromExample = isNew && search.get('start') === 'example';
  const exampleId = search.get('example') ?? '';
  const wantName = (search.get('name') ?? '').trim();
  const catalog = useCatalog();
  const strategy = useStrategy(sid, !isNew);
  const example = useExample(exampleId, fromExample && exampleId !== '');
  const wide = useMediaQuery(EDIT_MIN);
  const failed = catalog.isError || strategy.isError || example.isError;
  if (failed)
    return (
      <LoadError
        onRetry={() => {
          void catalog.refetch();
          if (!isNew) void strategy.refetch();
        }}
      />
    );
  const cat = catalog.data;
  if (!cat) return null;
  let start: EditorStart;
  if (!isNew) {
    const s = strategy.data;
    if (!s) return null;
    const savedNo = (location.state as { saved?: number } | null)?.saved;
    start = {
      sid: s.id,
      no: s.version.no,
      body: { name: s.name, graph: s.body.graph },
      toast: savedNo ? t.saved(savedNo) : null,
    };
  } else if (fromExample) {
    const ex = example.data;
    if (!ex) return null;
    start = { sid: null, no: null, body: { name: wantName || ex.name, graph: ex.body.graph } };
  } else {
    const body: Body = { name: wantName, graph: cat.blank.graph };
    start = { sid: null, no: null, body };
  }
  const key = isNew ? `new-${exampleId}-${wantName}` : `s-${String(sid)}`;
  if (!wide) return <NarrowView key={key} catalog={cat} start={start} />;
  return <CanvasEditor key={key} catalog={cat} start={start} />;
}
