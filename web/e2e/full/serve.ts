// One world of the full run: seeds a fresh engine database (dev-seed) and serves it with uvicorn,
// which serves the production build in web/dist itself (same origin, production CSP).
// Usage: node e2e/full/serve.ts <first-day|paper|discovery> <port>
// The database lives in web/build/e2e-full/ (git-ignored), never under data/. The server reads
// the world's clock (AUTOTRADE_FAKE_NOW, dev only) from dev-seed's answer.
import { spawn, spawnSync } from 'node:child_process';
import { mkdirSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const [world, port] = process.argv.slice(2);
if (!world || !port) {
  console.error('usage: node e2e/full/serve.ts <world> <port>');
  process.exit(2);
}

const web = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const repo = resolve(web, '..');
const dir = join(web, 'build', 'e2e-full');
const db = join(dir, `${world}.db`);
mkdirSync(dir, { recursive: true });
// dev-seed only ever creates a new database.
for (const file of [db, `${db}-wal`, `${db}-shm`, `${db}-journal`]) rmSync(file, { force: true });

/** The server's Python and packages (ops notes), without a project environment. */
const PYTHON = [
  'run',
  '--no-project',
  '--python',
  '3.10',
  '--with',
  'fastapi==0.136.1',
  '--with',
  'uvicorn==0.46.0',
  '--with',
  'pydantic==2.13.4',
  '--with',
  'httpx==0.28.1',
  '--with',
  'pandas==2.3.3',
  '--with',
  'numpy==2.2.6',
  'python',
  '-m',
];

const seed = spawnSync(
  'uv',
  [...PYTHON, 'autotrade.jobs', 'dev-seed', '--db', db, '--world', world],
  { cwd: repo, encoding: 'utf8' },
);
if (seed.status !== 0) {
  console.error(seed.stdout, seed.stderr);
  process.exit(seed.status ?? 1);
}
const summary = JSON.parse(
  seed.stdout.slice(seed.stdout.indexOf('{'), seed.stdout.lastIndexOf('}') + 1),
) as { now: string; result: string };
if (summary.result !== 'ok') {
  console.error(seed.stdout);
  process.exit(1);
}

const server = spawn(
  'uv',
  [...PYTHON, 'uvicorn', 'autotrade.api.app:app', '--host', '127.0.0.1', '--port', port],
  {
    cwd: repo,
    stdio: 'inherit',
    env: { ...process.env, AUTOTRADE_DEV: '1', AUTOTRADE_FAKE_NOW: summary.now, AUTOTRADE_DB: db },
  },
);
for (const signal of ['SIGINT', 'SIGTERM'] as const) {
  process.on(signal, () => {
    server.kill(signal);
  });
}
server.on('exit', (code) => {
  process.exit(code ?? 0);
});
