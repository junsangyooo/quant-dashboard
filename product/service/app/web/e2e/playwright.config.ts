// 금고 흐름 화면 시험(P1-02 ⑤ · QUALITY S5)의 Playwright 설정.
//
//   cd product/service/app && . /opt/session-env.sh && npx playwright test -c web/e2e/playwright.config.ts
//
// - 서버: `tests/e2e_server.py`(가짜 전송 · 지어낸 일봉 · 스케줄러 없음 · 127.0.0.1:8798 · 포트 8797(기준선) · 8799(compare.mjs)와
//   겹치지 않게). 데이터 폴더 · HOME · 키 파일 폴더는 운영체제 임시 폴더(끝나면 `teardown.ts`가 지움).
// - 브라우저: `PW_CHROMIUM`(없으면 `/opt/pw-browsers/chromium`) 실행 파일 · 내려받지 않아요. 브라우저에는 프록시 변수를 주지 않아요.
// - 화면은 `web/dist`(서버가 내줌) · `check.sh`는 build 뒤에 이 시험을 불러요.
import { defineConfig, devices } from '@playwright/test';
import { mkdirSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const APP = resolve(import.meta.dirname, '../..');
const PORT = 8798;
const PYTHON = process.env.QUANT_PYTHON ?? join(APP, '.venv', 'bin', 'python');
const CHROMIUM = process.env.PW_CHROMIUM ?? '/opt/pw-browsers/chromium';

// 이 설정 파일은 실행기와 일꾼 프로세스가 각각 읽어요. 임시 폴더는 처음 읽는 쪽(실행기)이 만들고 환경 변수로 넘겨
// 일꾼은 같은 것을 쓰게 해요(빈 폴더가 남지 않게). 끝나면 `teardown.ts`가 지워요.
process.env.QUANT_E2E_TMP_ROOT ??= mkdtempSync(join(tmpdir(), 'quant-e2e-'));
const root = process.env.QUANT_E2E_TMP_ROOT;
const home = join(root, 'home');
const data = join(root, 'data');
mkdirSync(home, { recursive: true });

const serverEnv: Record<string, string> = {};
const browserEnv: Record<string, string> = {};
for (const [k, v] of Object.entries(process.env)) {
  if (v === undefined) continue;
  serverEnv[k] = v;
  if (!/^(https?|all|no)_proxy$/i.test(k)) browserEnv[k] = v;
}
serverEnv.HOME = home;
serverEnv.QUANT_E2E_KEYFILE_DIR = join(home, 'kf');
delete serverEnv.QUANT_LIVE_TRANSPORT; // 늘 가짜 전송

export default defineConfig({
  testDir: '.',
  testMatch: /.*\.spec\.ts$/,
  globalTeardown: './teardown.ts',
  outputDir: resolve(APP, 'web/test-results/e2e'),
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [['list']],
  use: {
    ...devices['Desktop Chrome'],
    baseURL: `http://127.0.0.1:${PORT}`,
    launchOptions: { executablePath: CHROMIUM, env: browserEnv },
    viewport: { width: 1440, height: 1000 },
    locale: 'ko-KR',
    timezoneId: 'Asia/Seoul',
  },
  webServer: {
    command: `${PYTHON} -m tests.e2e_server ${data} ${PORT}`,
    url: `http://127.0.0.1:${PORT}/api/health`,
    cwd: APP,
    env: serverEnv,
    reuseExistingServer: false,
    timeout: 60_000,
    stdout: 'ignore',
    stderr: 'pipe',
  },
});
