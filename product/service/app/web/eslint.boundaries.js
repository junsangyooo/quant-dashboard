// 화면 경계(ARCHITECTURE 3절 · 7절 '화면 경계' · TASKS P1-04).
//
// 1단계에는 `ds/` · `features/` 폴더가 없어서 ARCHITECTURE 6절 '1단계 예외'대로 지금 폴더를 층에 붙여 세요:
// `screens/<기능>/` = features · `components/` · `charts/` = ds · `api/` · `copy/`(+ `copy.ts`) · `lib/` · `shell/`(+ `routes.tsx`) ·
// `main.tsx` = 조립(무엇이든) · `styles/` = 토큰. 층 표와 금지 표는 `app/tests/baseline/webcounts.py`(`layer_of` · `FORBIDDEN`)와
// 같아요 — 둘이 같은지는 `app/tests/test_structure_web.py`가 ESLint를 돌려 확인해요.
//
// 방법: `src/` 파일마다 금지 층에 있는 파일(지금 있는 ts · tsx · css)을 그 파일 자리에서 본 상대 지정자로 바꿔
// `no-restricted-imports`의 `regex` 패턴(정적 import · export-from)과 `no-restricted-syntax`의 `ImportExpression`(동적 import)에
// 넣어요. 지금 어긋난 (파일 → 대상) 쌍은 허용 목록 `app/tests/allow/web-boundaries.txt`에 있고 그 쌍만 패턴에서 빠져요.
// 쌍마다 몇 곳인지 · 목록이 줄어들기만 하는지는 pytest(`test_structure_web.py`)가 세요(ESLint는 쌍만 앎).
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

const WEB = import.meta.dirname;
const SRC = path.join(WEB, 'src');
export const ALLOW_FILE = path.join(WEB, '..', 'tests', 'allow', 'web-boundaries.txt');

// webcounts.FORBIDDEN 그대로(features → 다른 features는 아래에서 따로 · 같은 기능 안은 허용)
const FORBIDDEN = {
  ds: ['features', 'api', 'copy', 'shell'],
  api: ['ds', 'features', 'shell'],
  copy: ['ds', 'api', 'lib', 'features', 'shell', 'assembly', 'tokens', 'graph'],
  lib: ['ds', 'api', 'copy', 'features', 'shell'],
  features: ['shell'],
  shell: ['api'],
  assembly: [],
  tokens: ['ds', 'api', 'copy', 'lib', 'features', 'shell'],
  graph: [],
  other: [],
};

/** web/ 기준 경로 → [층, 기능 이름] (webcounts.layer_of와 같음). */
export function layerOf(r) {
  if (!r.startsWith('src/')) return ['other', null];
  const s = r.slice(4);
  if (s.startsWith('screens/')) {
    const rest = s.slice('screens/'.length);
    return ['features', rest.includes('/') ? rest.split('/')[0] : rest.replace(/\.[^.]*$/, '')];
  }
  if (s.startsWith('components/') || s.startsWith('charts/')) return ['ds', null];
  if (s.startsWith('api/')) return ['api', null];
  if (s.startsWith('copy/') || s === 'copy.ts') return ['copy', null];
  if (s.startsWith('lib/')) return ['lib', null];
  if (s.startsWith('shell/') || s === 'routes.tsx') return ['shell', null];
  if (s === 'main.tsx') return ['assembly', null];
  if (s.startsWith('styles/')) return ['tokens', null];
  if (s.startsWith('graph/')) return ['graph', null];
  return ['other', null];
}

function walk(dir, exts) {
  const out = [];
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p, exts));
    else if (exts.some((x) => e.name.endsWith(x)))
      out.push(path.relative(WEB, p).split(path.sep).join('/'));
  }
  return out.sort();
}

/** 허용 목록 → Set('from to'). 줄 = `from to 수  # 까닭`(web/ 기준 경로). */
export function readAllow(file = ALLOW_FILE) {
  const pairs = new Set();
  for (const raw of readFileSync(file, 'utf8').split('\n')) {
    const code = raw.split('#')[0].trim();
    if (!code) continue;
    const [from, to, n] = code.split(/\s+/);
    if (!from || !to || !/^\d+$/.test(n ?? ''))
      throw new Error(`허용 목록 줄을 읽을 수 없어요: ${raw}`);
    pairs.add(`${from} ${to}`);
  }
  return pairs;
}

/** 대상 파일을 `fromFile` 자리에서 부르는 지정자들(확장자 있음 · 없음 · index). */
function specifiers(fromFile, target) {
  let rel = path.posix.relative(path.posix.dirname(fromFile), target);
  if (!rel.startsWith('.')) rel = `./${rel}`;
  const out = [rel];
  const m = /^(.*)\.(ts|tsx)$/.exec(rel);
  if (m) {
    out.push(m[1]);
    const idx = /^(.*)\/index$/.exec(m[1]);
    if (idx) out.push(idx[1]);
  }
  return out;
}

const escape = (s) => s.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&');

function why(fromLayer, fromFeature, target) {
  const [tLayer, tFeature] = layerOf(target);
  if (FORBIDDEN[fromLayer].includes(tLayer)) return `${fromLayer} → ${tLayer}`;
  if (fromLayer === 'features' && tLayer === 'features' && tFeature !== fromFeature) {
    return 'features → 다른 features';
  }
  return null;
}

/** eslint.config.js에 펼쳐 넣는 설정들. `allow: false`면 허용 목록 없이(시험이 쓰는 셈 대조용). */
export function boundaryConfigs({ allow = true } = {}) {
  const allowed = allow ? readAllow() : new Set();
  const sources = walk(SRC, ['.ts', '.tsx']);
  const targets = walk(SRC, ['.ts', '.tsx', '.css']);
  const configs = [];
  for (const file of sources) {
    const [layer, feature] = layerOf(file);
    const byWhy = new Map();
    for (const t of targets) {
      const w = why(layer, feature, t);
      if (!w || allowed.has(`${file} ${t}`)) continue;
      if (!byWhy.has(w)) byWhy.set(w, []);
      byWhy.get(w).push(...specifiers(file, t).map(escape));
    }
    if (byWhy.size === 0) continue;
    const patterns = [];
    const selectors = [];
    for (const [w, alts] of byWhy) {
      const message = `화면 경계(ARCHITECTURE 3절 · 1단계는 지금 폴더로 셈 · 6절): ${w} 금지 · 허용 목록 app/tests/allow/web-boundaries.txt`;
      const re = `^(?:${alts.join('|')})$`;
      patterns.push({ regex: re, message, caseSensitive: true });
      selectors.push({ selector: `ImportExpression[source.value=/${re}/]`, message });
    }
    configs.push({
      files: [file],
      rules: {
        'no-restricted-imports': ['error', { patterns }],
        'no-restricted-syntax': ['error', ...selectors],
      },
    });
  }
  return configs;
}
