// 그림 비교(TASKS 머리 '그림 비교 기준'): 실제 서버(가짜 전송)를 켜 두고 같은 상태를 1440 · 390 폭으로 찍어
// 그림(design/frames)과 나란히 붙인 파일을 남겨요. 화면 글도 뽑아 함께 적어요.
//
//   node e2e/compare.mjs <base url> <out dir> <screen>   (screen: editor)
//
// 서버: MVP_PORT=8799 MVP_DATA_DIR=<빈 폴더> .venv/bin/python -m uvicorn --factory app.main:create_app \
//         --host 127.0.0.1 --port 8799
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { chromium } from 'playwright';

const [, , base = 'http://127.0.0.1:8799', outDir = 'compare', screen = 'editor', only = 'all'] =
  process.argv;
const FRAMES = resolve(import.meta.dirname, '../../../design/frames');
const PASSWORD = 'correct horse 9';

function blocks(opts = {}) {
  STATES.strategies = [
    {
      name: 'V2-20 전략 있음',
      frame: 'V2-20__전략_있음__1440__314-100364.png',
      path: '/strategies',
      go: async () => undefined,
    },
    {
      name: 'V2-21 새 전략 시트',
      frame: 'V2-21__기본__1440__328-135486.png',
      path: '/strategies',
      go: async (p) => p.getByRole('button', { name: '새 전략' }).click(),
    },
    {
      name: 'V2-22 확인',
      frame: 'V2-22__확인__1440__327-132753.png',
      path: '/strategies/import',
      go: async (p) => {
        const text = readFileSync(
          resolve(import.meta.dirname, '../../../examples/copy-v3-example.txt'),
          'utf8',
        );
        await p.getByRole('textbox').fill(text);
        await p.waitForTimeout(500);
      },
    },
    {
      name: 'V2-22 형식 아님',
      frame: 'V2-22__형식_아님__1440__345-258976.png',
      path: '/strategies/import',
      go: async (p) => {
        await p.getByRole('textbox').fill('quant-strategy/3 app>=1.0 아무 글');
        await p.waitForTimeout(500);
      },
    },
    {
      name: 'V2-25 운용 전',
      frame: 'V2-25__운용_전__1440__327-132945.png',
      path: '/strategies/ID',
      go: async () => undefined,
    },
  ];

  STATES.backtest = [
    {
      name: 'V2-26 입력',
      frame: 'V2-26__입력__1440__311-94832.png',
      path: '/strategies/ID/backtest',
      body: (r) => ({
        ...blocks({ filterRows: [r('turnover', 'gte', 1)] }),
        graph: {
          ...blocks({ filterRows: [r('turnover', 'gte', 1)] }).graph,
          blocks: blocks({ filterRows: [r('turnover', 'gte', 1)] }).graph.blocks.map((b) =>
            b.id === 'u'
              ? {
                  ...b,
                  rows: [
                    r('manual_list', 'pick', ['005930', '000660', '373220', '005380', '035420']),
                  ],
                }
              : b,
          ),
        },
      }),
      go: async () => undefined,
    },
    {
      name: 'V2-26 결과',
      frame: 'V2-26__결과__1440__311-95007.png',
      path: '/strategies/ID/backtest',
      body: (r) => ({
        ...blocks({ filterRows: [r('turnover', 'gte', 1)] }),
        graph: {
          ...blocks({ filterRows: [r('turnover', 'gte', 1)] }).graph,
          blocks: blocks({ filterRows: [r('turnover', 'gte', 1)] }).graph.blocks.map((b) =>
            b.id === 'u'
              ? {
                  ...b,
                  rows: [
                    r('manual_list', 'pick', ['005930', '000660', '373220', '005380', '035420']),
                  ],
                }
              : b,
          ),
        },
      }),
      go: async (p) => {
        await p.locator('input[type=date]').first().fill('2021-06-01');
        await p.locator('input[type=date]').nth(1).fill('2025-09-30');
        await p.getByRole('button', { name: '백테스트 실행' }).click();
        await p.waitForSelector('text=거래 목록', { timeout: 30000 });
      },
    },
  ];

  // 모의투자 탭: prep이 새 버전을 만들고(필요하면 모의투자를 시작하고) 열 경로를 돌려줘요
  async function paperPrep(ctx, id, { run = true } = {}) {
    const v = await (
      await ctx.request.post(`${base}/api/v2/strategies/${id}/versions`, {
        data: { body: blocks() },
      })
    ).json();
    if (!run) return { vid: v.version_id };
    const started = await (
      await ctx.request.post(`${base}/api/v2/paper/start`, {
        data: { version_id: v.version_id, cash: 10000000 },
      })
    ).json();
    await ctx.request.post(`${base}/api/v2/paper/check`);
    return { vid: v.version_id, rid: started.id ?? started.run_id };
  }

  STATES.paper = [
    {
      name: 'V2-40 있음',
      frame: 'V2-40__있음__1440__345-292339.png',
      prep: async (ctx, id) => (await paperPrep(ctx, id), '/paper'),
      go: async () => undefined,
    },
    {
      name: 'V2-41 모의투자 중',
      frame: 'V2-41__모의투자_중__1440__345-292548.png',
      prep: async (ctx, id) => `/paper/${(await paperPrep(ctx, id)).rid}`,
      go: async () => undefined,
    },
    {
      name: 'V2-42 기본',
      frame: 'V2-42__기본__1440__331-172322.png',
      prep: async (ctx, id) =>
        `/paper/start?version=${(await paperPrep(ctx, id, { run: false })).vid}`,
      go: async () => undefined,
    },
  ];

  const row = (item, op, value, extra = {}) => ({
    item,
    op,
    params: extra.params ?? {},
    value,
    value2: null,
    exec: extra.exec ?? null,
  });
  const filterRows = opts.filterRows ?? [
    row('turnover', 'gte', 50),
    row('per', 'lte', 15),
    row('debt_ratio', 'lte', 200),
  ];
  const sellRows = opts.sellRows ?? [
    row('stop_loss', 'fixed', 7, { exec: 'intraday' }),
    row('max_hold', 'fixed', 20, { exec: 'close' }),
  ];
  return {
    name: '대형주 돌파',
    graph: {
      blocks: [
        {
          id: 'u',
          stage: 'universe',
          match: 'all',
          x: 0,
          y: 0,
          rows: [
            row('market', 'pick', ['KOSPI', 'KOSDAQ']),
            row('exclude_preferred', 'exclude', null),
          ],
        },
        {
          id: 's',
          stage: 'signal',
          match: 'all',
          x: 304,
          y: 0,
          rows: [row('ma', 'cross_up', null, { params: { n: 20 } })],
        },
        { id: 'f', stage: 'filter', match: 'all', x: 608, y: 0, rows: filterRows },
        {
          id: 'k',
          stage: 'select',
          match: 'all',
          x: 0,
          y: 286,
          rows: [row('top_n', 'top_n', 5, { params: { by: 'strength', order: 'desc' } })],
        },
        {
          id: 'b',
          stage: 'buy',
          match: 'all',
          x: 304,
          y: 286,
          rows: [row('next_open', 'fixed', 1)],
        },
        { id: 'x', stage: 'sell', match: opts.sellMatch ?? 'any', x: 608, y: 286, rows: sellRows },
        {
          id: 'w',
          stage: 'weight',
          match: 'all',
          x: 0,
          y: 428,
          rows: [row('equal', 'fixed', null)],
        },
      ],
      edges: [
        { from: 'u', to: 's' },
        { from: 's', to: 'f' },
        { from: 'f', to: 'k' },
        { from: 'k', to: 'b' },
        { from: 'w', to: 'b' },
        { from: 'b', to: 'x' },
      ],
    },
  };
}

async function setup(ctx, { dart = true } = {}) {
  const r = ctx.request;
  await r.post(`${base}/api/setup`, {
    data: { password: PASSWORD, password2: PASSWORD, adult: true, terms: true },
  });
  await r.post(`${base}/api/login`, { data: { password: PASSWORD } });
  // 바꾸는 요청은 CSRF 값을 머리글로 되돌려 보내요(T-51)
  const csrf = (await ctx.cookies()).find((c) => c.name === 'qm_csrf');
  if (csrf) await ctx.setExtraHTTPHeaders({ 'x-csrf-token': csrf.value });
  if (dart) await r.put(`${base}/api/connect/dart`, { data: { key: 'fake-dart-key-0000' } });
  const made = await (
    await r.post(`${base}/api/v2/strategies`, { data: { body: blocks() } })
  ).json();
  for (let i = 0; i < 2; i++)
    await r.post(`${base}/api/v2/strategies/${made.id}/versions`, { data: { body: blocks() } });
  return made.id;
}

async function sideBySide(browser, shot, frame, file, width) {
  const page = await browser.newPage({ viewport: { width: width * 2 + 48, height: 1100 } });
  const a = readFileSync(shot).toString('base64');
  const b = readFileSync(join(FRAMES, frame)).toString('base64');
  await page.setContent(
    `<body style="margin:0;display:flex;gap:16px;padding:16px;background:#888">` +
      `<figure style="margin:0"><figcaption style="font:14px sans-serif;color:#fff">앱</figcaption>` +
      `<img src="data:image/png;base64,${a}" style="width:${width}px"></figure>` +
      `<figure style="margin:0"><figcaption style="font:14px sans-serif;color:#fff">그림 ${frame}</figcaption>` +
      `<img src="data:image/png;base64,${b}" style="width:${width}px"></figure></body>`,
  );
  await page.screenshot({ path: file, fullPage: true, type: 'jpeg', quality: 70 });
  await page.close();
}

const STATES = {
  editor: [
    {
      name: '기본(문제 없음)',
      frame: 'V2-23__기본(문제_없음)__1440__324-117378.png',
      go: async () => undefined,
    },
    {
      name: '문장으로 보기',
      frame: 'V2-23__문장으로_보기__1440__345-186346.png',
      go: async (p) => p.getByRole('button', { name: '문장으로 보기' }).click(),
    },
    {
      name: '조건 추가 메뉴-분류',
      frame: 'V2-23__조건_추가_메뉴-분류__1440__345-201134.png',
      go: async (p) => {
        await p.locator('[data-block="f"]').getByRole('button', { name: '조건 추가' }).click();
        await p.getByRole('button', { name: /가치/ }).click();
      },
    },
    {
      name: '줄 편집',
      frame: 'V2-23__줄_편집__1440__326-122715.png',
      go: async (p) => p.locator('[data-block="f"] [role="button"]').nth(1).click(),
    },
    {
      name: '실행 방식-고르기',
      frame: 'V2-23__실행_방식-고르기__1440__345-220695.png',
      go: async (p) => p.locator('[data-block="x"] [role="button"]').nth(0).click(),
    },
    {
      name: '문제 있음-문제 목록 펼침',
      frame: 'V2-23__문제_있음-문제_목록_펼침__1440__325-117895.png',
      body: (r) =>
        blocks({
          filterRows: [
            r('turnover', 'gte', 200000),
            r('per', 'lte', null),
            r('debt_ratio', 'lte', 200),
          ],
          sellRows: [
            r('stop_loss', 'fixed', 7, { exec: 'intraday' }),
            r('take_profit', 'fixed', 15, { exec: 'intraday' }),
            r('max_hold', 'fixed', 20, { exec: 'close' }),
          ],
          sellMatch: 'all',
        }),
      go: async (p) => p.getByRole('button', { name: /문제 2/ }).click(),
    },
    {
      name: '실행 방식-종가 확인으로 바뀜',
      frame: 'V2-23__실행_방식-종가_확인으로_바뀜__1440__345-221951.png',
      body: () => blocks({ sellMatch: 'all' }),
      go: async () => undefined,
    },
    {
      name: '빈 캔버스',
      frame: 'V2-23__빈_캔버스__1440__324-116962.png',
      path: '/strategies/new',
      go: async () => undefined,
    },
  ],
};

STATES.strategies = [
  {
    name: 'V2-20 전략 있음',
    frame: 'V2-20__전략_있음__1440__314-100364.png',
    path: '/strategies',
    go: async () => undefined,
  },
  {
    name: 'V2-21 새 전략 시트',
    frame: 'V2-21__기본__1440__328-135486.png',
    path: '/strategies',
    go: async (p) => p.getByRole('button', { name: '새 전략' }).click(),
  },
  {
    name: 'V2-22 확인',
    frame: 'V2-22__확인__1440__327-132753.png',
    path: '/strategies/import',
    go: async (p) => {
      const text = readFileSync(
        resolve(import.meta.dirname, '../../../examples/copy-v3-example.txt'),
        'utf8',
      );
      await p.getByRole('textbox').fill(text);
      await p.waitForTimeout(500);
    },
  },
  {
    name: 'V2-22 형식 아님',
    frame: 'V2-22__형식_아님__1440__345-258976.png',
    path: '/strategies/import',
    go: async (p) => {
      await p.getByRole('textbox').fill('quant-strategy/3 app>=1.0 아무 글');
      await p.waitForTimeout(500);
    },
  },
  {
    name: 'V2-25 운용 전',
    frame: 'V2-25__운용_전__1440__327-132945.png',
    path: '/strategies/ID',
    go: async () => undefined,
  },
];

STATES.backtest = [
  {
    name: 'V2-26 입력',
    frame: 'V2-26__입력__1440__311-94832.png',
    path: '/strategies/ID/backtest',
    body: (r) => ({
      ...blocks({ filterRows: [r('turnover', 'gte', 1)] }),
      graph: {
        ...blocks({ filterRows: [r('turnover', 'gte', 1)] }).graph,
        blocks: blocks({ filterRows: [r('turnover', 'gte', 1)] }).graph.blocks.map((b) =>
          b.id === 'u'
            ? {
                ...b,
                rows: [
                  r('manual_list', 'pick', ['005930', '000660', '373220', '005380', '035420']),
                ],
              }
            : b,
        ),
      },
    }),
    go: async () => undefined,
  },
  {
    name: 'V2-26 결과',
    frame: 'V2-26__결과__1440__311-95007.png',
    path: '/strategies/ID/backtest',
    body: (r) => ({
      ...blocks({ filterRows: [r('turnover', 'gte', 1)] }),
      graph: {
        ...blocks({ filterRows: [r('turnover', 'gte', 1)] }).graph,
        blocks: blocks({ filterRows: [r('turnover', 'gte', 1)] }).graph.blocks.map((b) =>
          b.id === 'u'
            ? {
                ...b,
                rows: [
                  r('manual_list', 'pick', ['005930', '000660', '373220', '005380', '035420']),
                ],
              }
            : b,
        ),
      },
    }),
    go: async (p) => {
      await p.locator('input[type=date]').first().fill('2021-06-01');
      await p.locator('input[type=date]').nth(1).fill('2025-09-30');
      await p.getByRole('button', { name: '백테스트 실행' }).click();
      await p.waitForSelector('text=거래 목록', { timeout: 30000 });
    },
  },
];

// 모의투자 탭: prep이 새 버전을 만들고(필요하면 모의투자를 시작하고) 열 경로를 돌려줘요
async function paperPrep(ctx, id, { run = true } = {}) {
  const v = await (
    await ctx.request.post(`${base}/api/v2/strategies/${id}/versions`, { data: { body: blocks() } })
  ).json();
  if (!run) return { vid: v.version_id };
  const started = await (
    await ctx.request.post(`${base}/api/v2/paper/start`, {
      data: { version_id: v.version_id, cash: 10000000 },
    })
  ).json();
  await ctx.request.post(`${base}/api/v2/paper/check`);
  return { vid: v.version_id, rid: started.id ?? started.run_id };
}

STATES.paper = [
  {
    name: 'V2-40 있음',
    frame: 'V2-40__있음__1440__345-292339.png',
    prep: async (ctx, id) => (await paperPrep(ctx, id), '/paper'),
    go: async () => undefined,
  },
  {
    name: 'V2-41 모의투자 중',
    frame: 'V2-41__모의투자_중__1440__345-292548.png',
    prep: async (ctx, id) => `/paper/${(await paperPrep(ctx, id)).rid}`,
    go: async () => undefined,
  },
  {
    name: 'V2-42 기본',
    frame: 'V2-42__기본__1440__331-172322.png',
    prep: async (ctx, id) =>
      `/paper/start?version=${(await paperPrep(ctx, id, { run: false })).vid}`,
    go: async () => undefined,
  },
];

const row = (item, op, value, extra = {}) => ({
  item,
  op,
  params: extra.params ?? {},
  value,
  value2: null,
  exec: extra.exec ?? null,
});

mkdirSync(outDir, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.PW_CHROMIUM ?? '/opt/pw-browsers/chromium',
});
const report = [];
for (const [k, st] of STATES[screen].entries()) {
  if (only !== 'all' && only !== String(k)) continue;
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    locale: 'ko-KR',
  });
  const id = await setup(ctx);
  if (st.body)
    await ctx.request.post(`${base}/api/v2/strategies/${id}/versions`, {
      data: { body: st.body(row) },
    });
  const path = st.prep ? await st.prep(ctx, id) : st.path;
  const page = await ctx.newPage();
  await page.goto(`${base}${(path ?? `/strategies/${id}/edit`).replace('ID', String(id))}`);
  await page.waitForSelector(screen === 'editor' ? '[data-block]' : 'main h1');
  await page.waitForTimeout(400);
  await st.go(page);
  await page.waitForTimeout(400);
  const slug = st.name.replace(/[^\w가-힣()-]+/g, '_');
  const shot = join(outDir, `${slug}__app.png`);
  await page.screenshot({ path: shot, fullPage: screen !== 'editor' });
  const text = await page.locator('main').innerText();
  writeFileSync(join(outDir, `${slug}__text.txt`), text);
  await sideBySide(
    browser,
    shot,
    st.frame,
    join(outDir, `${screen === 'editor' ? 'V2-23__' : ''}${slug}__1440__compare.jpg`),
    1440 / 2,
  );
  report.push({ name: st.name, frame: st.frame });
  await ctx.close();
  // 다음 상태는 새 데이터 폴더가 필요해요: 서버를 상태마다 새로 켜는 대신 이름이 겹치지 않게 그냥 이어서 만들어요
}
// 390: 좁은 창(보기만)
if (screen === 'editor' && (only === 'all' || only === 'narrow')) {
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    locale: 'ko-KR',
  });
  const id = await setup(ctx);
  const page = await ctx.newPage();
  await page.goto(`${base}/strategies/${id}/edit`);
  await page.waitForTimeout(800);
  const shot = join(outDir, 'V2-24_보기만__app.png');
  await page.screenshot({ path: shot, fullPage: false });
  await sideBySide(
    browser,
    shot,
    'V2-24__보기만__390__329-136085.png',
    join(outDir, 'V2-24__보기만__390__compare.jpg'),
    390,
  );
  report.push({ name: '보기만 390', frame: 'V2-24__보기만__390__329-136085.png' });
  await ctx.close();
}
await browser.close();
writeFileSync(join(outDir, 'report.json'), JSON.stringify(report, null, 1));
console.log(`${report.length} states → ${outDir}`);
