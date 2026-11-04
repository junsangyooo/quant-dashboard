// 화면 기준선 찍기(P1-01c): `web/e2e/compare.mjs`의 화면 목록을 **상태 하나 × 1440 · 390 두 폭**으로 다시 꾸려,
// 상태마다 새 서버(가짜 전송 · 빈 데이터 폴더 · 고정 시각 · `tests/baseline/screen_server.py`)를 켜고
// Playwright로 PNG · 화면 글(`document.body.innerText`) · 역할 트리(aria snapshot)를 남겨요.
//
//   node tests/baseline/screens.mjs list
//   node tests/baseline/screens.mjs capture --out DIR --python PY --now-ms N [--only GROUP[:INDEX]] [--widths 1440,390] [--port 8797]
//   node tests/baseline/screens.mjs diff PAIRS.json        (PNG 두 장의 픽셀 차 % · 브라우저 canvas로 셈)
//
// 바깥 요청: `ctx.route`로 서버(127.0.0.1:포트) 밖 요청을 모두 막고 세요(1건이라도 있으면 찍기 실패 · `screens.json`에 수를 남김).
// 두 번 같게 찍는 장치: 서버 · 페이지 시각 고정(`page.clock.setFixedTime`) · 복구 코드 씨앗(서버) · `reducedMotion` ·
// `timezoneId: Asia/Seoul` · 글꼴 로딩 기다림(`document.fonts.ready` · 동작 뒤에도) · 애니메이션 끔 · 커서 숨김
// (`screenshot({ animations: 'disabled', caret: 'hide' })`) · 상태마다 새 서버라 앞 상태의 자료가 섞이지 않음.
// 브라우저는 `PW_CHROMIUM`(내려받지 않음). Node 패키지는 `web/node_modules`의 playwright를 그대로 써요.
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { basename, join, resolve } from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const APP = resolve(import.meta.dirname, '../..'); // product/service/app
const WEB = join(APP, 'web');
const { chromium } = createRequire(join(WEB, 'package.json'))('playwright');
const PASSWORD = 'correct horse 9';
const WIDTHS = { 1440: { viewport: { width: 1440, height: 1000 }, scale: 1 }, 390: { viewport: { width: 390, height: 844 }, scale: 2 } };

// ── 전략 본문(compare.mjs와 같음) ─────────────────────────────────────────────
const row = (item, op, value, extra = {}) => ({ item, op, params: extra.params ?? {}, value, value2: null, exec: extra.exec ?? null });

function blocks(opts = {}) {
  const filterRows = opts.filterRows ?? [row('turnover', 'gte', 50), row('per', 'lte', 15), row('debt_ratio', 'lte', 200)];
  const sellRows = opts.sellRows ?? [row('stop_loss', 'fixed', 7, { exec: 'intraday' }), row('max_hold', 'fixed', 20, { exec: 'close' })];
  return {
    name: '대형주 돌파',
    graph: {
      blocks: [
        { id: 'u', stage: 'universe', match: 'all', x: 0, y: 0, rows: [row('market', 'pick', ['KOSPI', 'KOSDAQ']), row('exclude_preferred', 'exclude', null)] },
        { id: 's', stage: 'signal', match: 'all', x: 304, y: 0, rows: [row('ma', 'cross_up', null, { params: { n: 20 } })] },
        { id: 'f', stage: 'filter', match: 'all', x: 608, y: 0, rows: filterRows },
        { id: 'k', stage: 'select', match: 'all', x: 0, y: 286, rows: [row('top_n', 'top_n', 5, { params: { by: 'strength', order: 'desc' } })] },
        { id: 'b', stage: 'buy', match: 'all', x: 304, y: 286, rows: [row('next_open', 'fixed', 1)] },
        { id: 'x', stage: 'sell', match: opts.sellMatch ?? 'any', x: 608, y: 286, rows: sellRows },
        { id: 'w', stage: 'weight', match: 'all', x: 0, y: 428, rows: [row('equal', 'fixed', null)] },
      ],
      edges: [{ from: 'u', to: 's' }, { from: 's', to: 'f' }, { from: 'f', to: 'k' }, { from: 'k', to: 'b' }, { from: 'w', to: 'b' }, { from: 'b', to: 'x' }],
    },
  };
}

const backtestBody = (r) => {
  const b = blocks({ filterRows: [r('turnover', 'gte', 1)] });
  return {
    ...b,
    graph: { ...b.graph, blocks: b.graph.blocks.map((x) => (x.id === 'u' ? { ...x, rows: [r('manual_list', 'pick', ['005930', '000660', '373220', '005380', '035420'])] } : x)) },
  };
};

const COPY_EXAMPLE = resolve(APP, '../examples/copy-v3-example.txt');
const fillSetup = async (p) => {
  await p.getByLabel('비밀번호', { exact: true }).fill(PASSWORD);
  await p.getByLabel('비밀번호 다시 입력').fill(PASSWORD);
  await p.getByText('만 19세 이상이에요').click();
  await p.getByText('사용 조건에 모두 동의해요').click();
};
const placeServer = async (ctx, base) => {
  await ctx.request.put(`${base}/api/access/place`, { data: { place: 'server' } });
};
async function paperPrep(ctx, base, id, { run = true } = {}) {
  const v = await (await ctx.request.post(`${base}/api/v2/strategies/${id}/versions`, { data: { body: blocks() } })).json();
  if (!run) return { vid: v.version_id };
  const started = await (await ctx.request.post(`${base}/api/v2/paper/start`, { data: { version_id: v.version_id, cash: 10000000 } })).json();
  await ctx.request.post(`${base}/api/v2/paper/check`);
  return { vid: v.version_id, rid: started.id ?? started.run_id };
}

// ── 화면 목록: compare.mjs의 묶음 6개 · 390 전용 항목은 같은 상태의 390 그림으로 합쳤어요 ──────────────
// frames: { 1440: 그림 파일, 390: 그림 파일 }(없으면 그 폭의 그림 짝 없음) · path 'ID'는 전략 id · 기본 path는 편집기
export const STATES = {
  editor: [
    { name: '기본(문제 없음)', frames: { 1440: 'V2-23__기본(문제_없음)__1440__324-117378.png', 390: 'V2-24__보기만__390__329-136085.png' }, go: async () => undefined },
    { name: '문장으로 보기', only1440: '390은 보기만(V2-24) · 동작할 단추 · 줄이 없음', frames: { 1440: 'V2-23__문장으로_보기__1440__345-186346.png' }, go: async (p) => p.getByRole('button', { name: '문장으로 보기' }).click() },
    { name: '조건 추가 메뉴-분류', only1440: '390은 보기만(V2-24) · 동작할 단추 · 줄이 없음', frames: { 1440: 'V2-23__조건_추가_메뉴-분류__1440__345-201134.png' },
      go: async (p) => { await p.locator('[data-block="f"]').getByRole('button', { name: '조건 추가' }).click(); await p.getByRole('button', { name: /가치/ }).click(); } },
    { name: '줄 편집', only1440: '390은 보기만(V2-24) · 동작할 단추 · 줄이 없음', frames: { 1440: 'V2-23__줄_편집__1440__326-122715.png' }, go: async (p) => p.locator('[data-block="f"] [role="button"]').nth(1).click() },
    { name: '실행 방식-고르기', only1440: '390은 보기만(V2-24) · 동작할 단추 · 줄이 없음', frames: { 1440: 'V2-23__실행_방식-고르기__1440__345-220695.png' }, go: async (p) => p.locator('[data-block="x"] [role="button"]').nth(0).click() },
    { name: '문제 있음-문제 목록 펼침', only1440: '390은 보기만(V2-24) · 동작할 단추 · 줄이 없음', frames: { 1440: 'V2-23__문제_있음-문제_목록_펼침__1440__325-117895.png' },
      body: (r) => blocks({ filterRows: [r('turnover', 'gte', 200000), r('per', 'lte', null), r('debt_ratio', 'lte', 200)],
        sellRows: [r('stop_loss', 'fixed', 7, { exec: 'intraday' }), r('take_profit', 'fixed', 15, { exec: 'intraday' }), r('max_hold', 'fixed', 20, { exec: 'close' })], sellMatch: 'all' }),
      go: async (p) => p.getByRole('button', { name: /문제 2/ }).click() },
    { name: '실행 방식-종가 확인으로 바뀜', frames: { 1440: 'V2-23__실행_방식-종가_확인으로_바뀜__1440__345-221951.png' }, body: () => blocks({ sellMatch: 'all' }), go: async () => undefined },
    { name: '빈 캔버스', frames: { 1440: 'V2-23__빈_캔버스__1440__324-116962.png' }, path: '/strategies/new', go: async () => undefined },
  ],
  strategies: [
    { name: 'V2-20 전략 있음', frames: { 1440: 'V2-20__전략_있음__1440__314-100364.png' }, path: '/strategies', go: async () => undefined },
    { name: 'V2-21 새 전략 시트', frames: { 1440: 'V2-21__기본__1440__328-135486.png' }, path: '/strategies', go: async (p) => p.getByRole('button', { name: '새 전략' }).click() },
    { name: 'V2-22 확인', frames: { 1440: 'V2-22__확인__1440__327-132753.png' }, path: '/strategies/import',
      go: async (p) => { await p.getByRole('textbox').fill(readFileSync(COPY_EXAMPLE, 'utf8')); await p.waitForTimeout(500); } },
    { name: 'V2-22 형식 아님', frames: { 1440: 'V2-22__형식_아님__1440__345-258976.png' }, path: '/strategies/import',
      go: async (p) => { await p.getByRole('textbox').fill('quant-strategy/3 app>=1.0 아무 글'); await p.waitForTimeout(500); } },
    { name: 'V2-25 운용 전', frames: { 1440: 'V2-25__운용_전__1440__327-132945.png' }, path: '/strategies/ID', go: async () => undefined },
  ],
  backtest: [
    { name: 'V2-26 입력', frames: { 1440: 'V2-26__입력__1440__311-94832.png' }, path: '/strategies/ID/backtest', body: backtestBody, go: async () => undefined },
    { name: 'V2-26 결과', frames: { 1440: 'V2-26__결과__1440__311-95007.png' }, path: '/strategies/ID/backtest', body: backtestBody,
      go: async (p) => {
        await p.locator('input[type=date]').first().fill('2021-06-01');
        await p.locator('input[type=date]').nth(1).fill('2025-09-30');
        await p.getByRole('button', { name: '백테스트 실행' }).click();
        await p.waitForSelector('text=거래 목록', { timeout: 30000 });
      } },
  ],
  paper: [
    { name: 'V2-40 있음', frames: { 1440: 'V2-40__있음__1440__345-292339.png' }, prep: async (ctx, base, id) => (await paperPrep(ctx, base, id), '/paper'), go: async () => undefined },
    { name: 'V2-41 모의투자 중', frames: { 1440: 'V2-41__모의투자_중__1440__345-292548.png' }, prep: async (ctx, base, id) => `/paper/${(await paperPrep(ctx, base, id)).rid}`, go: async () => undefined },
    { name: 'V2-42 기본', frames: { 1440: 'V2-42__기본__1440__331-172322.png' }, prep: async (ctx, base, id) => `/paper/start?version=${(await paperPrep(ctx, base, id, { run: false })).vid}`, go: async () => undefined },
  ],
  settings: [
    { name: 'V2-01 기본', frames: { 1440: 'V2-01__기본__1440__331-171447.png', 390: 'V2-01__기본__390__303-87237.png' }, path: '/setup', fresh: true, go: async () => undefined },
    { name: 'V2-02 기본', frames: { 1440: 'V2-02__기본__1440__331-171544.png' }, path: '/setup', fresh: true,
      go: async (p) => { await fillSetup(p); await p.getByRole('button', { name: '다음' }).click(); await p.waitForSelector('text=복구 코드 쓰는 곳'); } },
    { name: 'V2-03 기본', frames: { 1440: 'V2-03__기본__1440__313-95664.png', 390: 'V2-03__기본__390__303-87443.png' }, path: '/login', loggedOut: true, go: async () => undefined },
    { name: 'V2-05 고르기 전', frames: { 1440: 'V2-05__고르기_전__1440__345-255899.png' }, path: '/setup/place', go: async () => undefined },
    { name: 'V2-06 서버-안 보임', frames: { 1440: 'V2-06__서버-안_보임__1440__345-256183.png' }, prep: async (ctx, base) => (await placeServer(ctx, base), '/setup/tailscale'), go: async () => undefined },
    { name: 'V2-08 토큰 없음', frames: { 1440: 'V2-08__토큰_없음__1440__345-257777.png' }, path: '/setup/telegram', go: async () => undefined },
    { name: 'V2-09 없음', frames: { 1440: 'V2-09__없음__1440__345-258336.png' }, path: '/setup/dart', noDart: true, go: async () => undefined },
    { name: 'V2-50 기본', frames: { 1440: 'V2-50__기본__1440__331-171688.png', 390: 'V2-50__기본__390__305-87696.png' }, prep: async (ctx, base) => (await placeServer(ctx, base), '/settings'), go: async () => undefined },
    { name: 'V2-52 연결 안 됨', frames: { 1440: 'V2-52__연결_안_됨__1440__345-291229.png' }, path: '/settings/notify', go: async () => undefined },
    { name: 'V2-53 기본', frames: { 1440: 'V2-53__기본__1440__345-292096.png' }, path: '/settings/data', go: async () => undefined },
    { name: 'V2-55 앱 정보-기본', frames: { 1440: 'V2-55__앱_정보-기본__1440__345-293060.png' }, prep: async (ctx, base) => (await placeServer(ctx, base), '/settings/about'), go: async () => undefined },
    { name: 'V2-56 Tailscale 안 보임', frames: { 1440: 'V2-56__Tailscale_안_보임__1440__345-293245.png' }, prep: async (ctx, base) => (await placeServer(ctx, base), '/settings/access'), go: async () => undefined },
  ],
  live: [
    { name: 'V2-10 운용 중', frames: { 1440: 'V2-10__운용_중__1440__331-166011.png', 390: 'V2-10__운용_중__390__331-166343.png' }, path: '/', go: async () => undefined },
    { name: 'V2-11 계획 있음', frames: { 1440: 'V2-11__계획_있음__1440__314-98796.png', 390: 'V2-11__계획_있음__390__306-89580.png' }, path: '/plan', go: async () => undefined },
    { name: 'V2-12 거래 있음', frames: { 1440: 'V2-12__거래_있음__1440__314-99712.png' }, path: '/history', go: async () => undefined },
    { name: 'V2-14 열림-결과 모르는 주문', frames: { 1440: 'V2-14__열림-결과_모르는_주문__1440__345-255212.png' }, path: '/todos', go: async (p) => p.getByText('결과 모르는 주문 [현대차]').click() },
    { name: 'V2-30 확인 ✕ 있음', frames: { 1440: 'V2-30__확인_✕_있음__1440__345-259530.png' }, path: '/live/start?version=1', go: async () => undefined },
    // compare.mjs도 멈추기 창의 그림 짝으로 V2-10 그림을 썼어요(멈추기 시트 그림은 따로 없음)
    { name: 'V2-32 멈추기', frames: { 1440: 'V2-10__운용_중__1440__331-166011.png' }, path: '/', go: async (p) => p.getByRole('button', { name: '멈추기 ›' }).click() },
  ],
};

const slug = (s) => s.replace(/[^\w가-힣()-]+/g, '_');
export function listStates() {
  const out = [];
  for (const [group, states] of Object.entries(STATES))
    states.forEach((st, i) => out.push({
      id: `${group}-${String(i).padStart(2, '0')}-${slug(st.name)}`, group, index: i, name: st.name, frames: st.frames,
      path: st.path ?? (group === 'editor' ? '/strategies/ID/edit' : (st.prep ? '(prep)' : null)), only1440: st.only1440 ?? null,
      fresh: !!st.fresh, loggedOut: !!st.loggedOut, noDart: !!st.noDart, hasBody: !!st.body, live: group === 'live',
      fullPage1440: group !== 'editor', // 1440 편집기는 캔버스가 창 안에서 스크롤 · 그 밖(390 보기만 포함)은 전체 페이지
    }));
  return out;
}

// 브라우저: `PW_CHROMIUM`(내려받지 않음) · 프록시 환경 변수를 비우고 배경 통신을 꺼서 브라우저 자체가 바깥(예: google)에
// 닿지 않게 해요(앱은 127.0.0.1 · 앱의 바깥 전송은 가짜).
function launch() {
  const env = { ...process.env };
  for (const k of Object.keys(env)) if (/^(https?|all|no)_proxy$/i.test(k)) delete env[k];
  return chromium.launch({
    executablePath: process.env.PW_CHROMIUM ?? '/opt/pw-browsers/chromium', env,
    args: ['--no-proxy-server', '--disable-background-networking', '--disable-component-update', '--disable-sync'],
  });
}

// ── 서버 ─────────────────────────────────────────────────────────────────────
function portFree(port) {
  return new Promise((res) => {
    const s = createServer();
    s.once('error', () => res(false));
    s.listen(port, '127.0.0.1', () => s.close(() => res(true)));
  });
}

// 포트는 고정(기본 8797): 앱 정보 화면(V2-55)이 `127.0.0.1:<포트>`를 보여 줘서 포트가 바뀌면 화면 글이 달라져요.
// 앞 서버가 끝나며 포트를 놓을 때까지 잠깐 기다려요(최대 30초).
async function startServer(python, live, port) {
  const dataDir = mkdtempSync(join(tmpdir(), 'quant-baseline-screens-'));
  const home = mkdtempSync(join(tmpdir(), 'quant-baseline-home-'));
  for (let i = 0; ; i++) {
    if (await portFree(port)) break;
    if (i >= 300) throw new Error(`포트 ${port}가 비지 않아요(다른 서버가 쓰는 중) · --port 로 바꿀 수 있어요`);
    await new Promise((r) => setTimeout(r, 100));
  }
  const args = ['-m', 'tests.baseline.screen_server', dataDir, String(port), ...(live ? ['live'] : [])];
  // HOME · 키 파일 폴더는 임시 폴더(stop()이 지움 · 키 파일이 /tmp에 남지 않게)
  const proc = spawn(python, args, { cwd: APP, env: { ...process.env, HOME: home, QUANT_BASELINE_KEYFILE_DIR: join(home, 'kf') }, stdio: ['ignore', 'pipe', 'pipe'] });
  let err = '';
  proc.stderr.on('data', (d) => { err += d.toString(); });
  const base = `http://127.0.0.1:${port}`;
  const t0 = Date.now();
  for (;;) {
    if (proc.exitCode !== null) throw new Error(`서버가 바로 꺼졌어요(exit ${proc.exitCode}):\n${err.slice(-2000)}`);
    try { const r = await fetch(`${base}/api/state`); if (r.status < 500) break; } catch { /* 아직 */ }
    if (Date.now() - t0 > 60000) { proc.kill('SIGKILL'); throw new Error(`서버가 60초 안에 응답하지 않아요:\n${err.slice(-2000)}`); }
    await new Promise((r) => setTimeout(r, 100));
  }
  const stop = async () => {
    proc.kill('SIGTERM');
    await new Promise((r) => {
      const timer = setTimeout(() => { proc.kill('SIGKILL'); r(); }, 10000);
      proc.on('exit', () => { clearTimeout(timer); r(); });
    });
    rmSync(dataDir, { recursive: true, force: true });
    rmSync(home, { recursive: true, force: true });
  };
  return { base, stop };
}

async function setup(ctx, base, { dart = true } = {}) {
  const r = ctx.request;
  await r.post(`${base}/api/setup`, { data: { password: PASSWORD, password2: PASSWORD, adult: true, terms: true } });
  await r.post(`${base}/api/login`, { data: { password: PASSWORD } });
  const csrf = (await ctx.cookies()).find((c) => c.name === 'qm_csrf');
  if (csrf) await ctx.setExtraHTTPHeaders({ 'x-csrf-token': csrf.value });
  if (dart) await r.put(`${base}/api/connect/dart`, { data: { key: 'fake-dart-key-0000' } });
  const made = await (await r.post(`${base}/api/v2/strategies`, { data: { body: blocks() } })).json();
  for (let i = 0; i < 2; i++) await r.post(`${base}/api/v2/strategies/${made.id}/versions`, { data: { body: blocks() } });
  return made.id;
}

// 글꼴(동적 서브셋이라 새 글이 보이면 새 조각을 받아요) · 레이아웃이 가라앉을 때까지: fonts.ready → 400ms → fonts.ready →
// 그림 두 프레임 → 300ms(팝오버처럼 JS가 자리를 재는 것이 끝나게)
const settled = async (page) => {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  await page.waitForTimeout(300);
};

async function captureOne(browser, python, nowMs, meta, st, width, outDir, port) {
  const { viewport, scale } = WIDTHS[width];
  const server = await startServer(python, meta.live, port);
  const rec = { id: meta.id, group: meta.group, name: meta.name, width, scale, viewport, png: `${meta.id}__${width}.png`, frame: st.frames[width] ?? null };
  try {
    const ctx = await browser.newContext({ viewport, deviceScaleFactor: scale, locale: 'ko-KR', timezoneId: 'Asia/Seoul', reducedMotion: 'reduce', colorScheme: 'light' });
    await ctx.clock.setFixedTime(nowMs);
    const base = server.base;
    // 바깥 요청 차단: 페이지가 서버(127.0.0.1:포트) 밖으로 내는 요청은 모두 막고 적어요(1건이라도 있으면 찍기 실패)
    const outbound = [];
    await ctx.route('**/*', (route) => {
      const url = route.request().url();
      if (url.startsWith(`${base}/`)) return route.continue();
      outbound.push(url);
      return route.abort('blockedbyclient');
    });
    rec.outbound = outbound;
    const id = st.fresh ? 0 : await setup(ctx, base, { dart: !st.noDart });
    if (st.loggedOut) await ctx.request.post(`${base}/api/logout`);
    if (st.body) await ctx.request.post(`${base}/api/v2/strategies/${id}/versions`, { data: { body: st.body(row) } });
    const path = st.prep ? await st.prep(ctx, base, id) : st.path;
    const page = await ctx.newPage();
    page.setDefaultTimeout(15000);
    await page.goto(`${base}${(path ?? `/strategies/${id}/edit`).replace('ID', String(id))}`);
    try {
      // 390 편집기는 '보기만'(V2-24)이라 블록(`[data-block]`)이 없어요 → compare.mjs처럼 main만 기다려요
      await page.waitForSelector(meta.group === 'editor' && width === 1440 ? '[data-block]' : 'main');
      await settled(page);
      await st.go(page);
      await page.mouse.move(0, 0); // 누른 단추 위에 마우스가 남아 hover 상태가 찍히지 않게(기준선은 hover 없음)
    } catch (e) {
      // 390 편집기는 1440의 동작(단추 · 줄)이 없을 수 있어요 → 까닭을 적고 그 화면은 비워 둬요(보고 B)
      rec.skipped = `동작 실패: ${String(e.message ?? e).split('\n')[0].slice(0, 160)}`;
      await ctx.close();
      return rec;
    }
    await settled(page);
    await page.screenshot({ path: join(outDir, rec.png), fullPage: width !== 1440 || meta.fullPage1440, animations: 'disabled', caret: 'hide', type: 'png' });
    rec.text = await page.evaluate(() => document.body.innerText);
    rec.aria = await page.locator('body').ariaSnapshot();
    await ctx.close();
    if (outbound.length) throw new Error(`바깥 요청 ${outbound.length}건(화면이 바깥 자원에 기대요 · 고치지 말고 보고): ${rec.id} ${width} · ${outbound.slice(0, 5).join(' · ')}`);
  } finally {
    await server.stop();
  }
  return rec;
}

async function capture(args) {
  const outDir = resolve(args.out);
  const python = args.python ?? join(APP, '.venv', 'bin', 'python');
  const nowMs = Number(args['now-ms']);
  if (!Number.isFinite(nowMs)) throw new Error('--now-ms 가 필요해요(tests/baseline/clock.FIXED_NOW_EPOCH_MS)');
  const widths = (args.widths ?? '1440,390').split(',').map(Number);
  const [onlyGroup, onlyIndex] = (args.only ?? '').split(':');
  mkdirSync(outDir, { recursive: true });
  const browser = await launch();
  const version = browser.version();
  const records = [];
  try {
    for (const meta of listStates()) {
      if (onlyGroup && meta.group !== onlyGroup) continue;
      if (onlyIndex !== undefined && onlyIndex !== '' && String(meta.index) !== onlyIndex) continue;
      const st = STATES[meta.group][meta.index];
      for (const width of widths) {
        const t0 = Date.now();
        if (width !== 1440 && st.only1440) {
          records.push({ id: meta.id, group: meta.group, name: meta.name, width, png: null, frame: st.frames[width] ?? null, skipped: st.only1440 });
          continue;
        }
        const rec = await captureOne(browser, python, nowMs, meta, st, width, outDir, Number(args.port ?? 8797));
        records.push(rec);
        if (!args.quiet) console.error(`${rec.id} ${width} ${rec.skipped ? '(건너뜀) ' + rec.skipped : 'ok'} ${((Date.now() - t0) / 1000).toFixed(1)}s`);
      }
    }
  } finally {
    await browser.close();
  }
  writeFileSync(join(outDir, 'screens_raw.json'), JSON.stringify({ browser: version, records }, null, 1));
  console.log(`${records.length} screens → ${basename(outDir)}`);
}

// ── 픽셀 차(두 PNG · 같은 자리의 RGBA가 다른 픽셀 수 / 큰 쪽 면적 · 크기가 다르면 빈 자리는 다른 픽셀로) ──
async function diff(pairsFile) {
  const pairs = JSON.parse(readFileSync(pairsFile, 'utf8'));
  const browser = await launch();
  const page = await browser.newPage();
  await page.setContent('<html><body></body></html>');
  const out = [];
  for (const p of pairs) {
    const a = existsSync(p.a) ? readFileSync(p.a).toString('base64') : null;
    const b = existsSync(p.b) ? readFileSync(p.b).toString('base64') : null;
    if (a === null || b === null) { out.push({ id: p.id, percent: 100, missing: a === null ? 'a' : 'b' }); continue; }
    const r = await page.evaluate(async ([a, b]) => {
      const load = (s) => new Promise((res, rej) => { const im = new Image(); im.onload = () => res(im); im.onerror = rej; im.src = 'data:image/png;base64,' + s; });
      const [ia, ib] = await Promise.all([load(a), load(b)]);
      const data = (im) => { const c = document.createElement('canvas'); c.width = im.width; c.height = im.height; const g = c.getContext('2d', { willReadFrequently: true }); g.drawImage(im, 0, 0); return g.getImageData(0, 0, im.width, im.height).data; };
      const da = data(ia), db = data(ib);
      const W = Math.max(ia.width, ib.width), H = Math.max(ia.height, ib.height);
      let changed = 0, x0 = W, y0 = H, x1 = -1, y1 = -1;
      const mark = (x, y) => { changed++; if (x < x0) x0 = x; if (y < y0) y0 = y; if (x > x1) x1 = x; if (y > y1) y1 = y; };
      for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
        if (x >= ia.width || y >= ia.height || x >= ib.width || y >= ib.height) { mark(x, y); continue; }
        const i = (y * ia.width + x) * 4, j = (y * ib.width + x) * 4;
        if (da[i] !== db[j] || da[i + 1] !== db[j + 1] || da[i + 2] !== db[j + 2] || da[i + 3] !== db[j + 3]) mark(x, y);
      }
      // bbox: 다른 픽셀을 모두 품는 사각형 [x0, y0, x1, y1](없으면 null) · 어디가 달라졌는지 찾을 때
      return { a: [ia.width, ia.height], b: [ib.width, ib.height], changed, total: W * H, bbox: changed ? [x0, y0, x1, y1] : null };
    }, [a, b]);
    out.push({ id: p.id, ...r, percent: Math.round((r.changed / r.total) * 100000) / 1000 });
  }
  await browser.close();
  console.log(JSON.stringify(out));
}

// 명령줄(모듈로 import하면 돌지 않아요 · STATES · listStates만 씀)
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [, , cmd, ...rest] = process.argv;
  const args = {};
  for (let i = 0; i < rest.length; i++) {
    if (rest[i].startsWith('--')) { const k = rest[i].slice(2); const v = rest[i + 1] && !rest[i + 1].startsWith('--') ? rest[++i] : true; args[k] = v; }
    else args._ = [...(args._ ?? []), rest[i]];
  }
  if (cmd === 'list') console.log(JSON.stringify(listStates(), null, 1));
  else if (cmd === 'capture') await capture(args);
  else if (cmd === 'diff') await diff(args._[0]);
  else { console.error('usage: screens.mjs list | capture --out DIR --python PY --now-ms N [--only G[:I]] | diff PAIRS.json'); process.exit(2); }
}
