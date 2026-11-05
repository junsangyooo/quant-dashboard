// Token pipeline (TASKS P1-12): the Figma export + design/tokens-scope.json → design/tokens.json
// → src/styles/tokens.css. Runs on Node's built-in type stripping: `node scripts/gen-tokens.ts`.
// `--check` writes nothing and exits 1 when a committed file differs from what it would write.
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  buildTokensCss,
  buildTokensJson,
  tokensJsonText,
  type FigmaExport,
  type TokenScope,
} from './tokens-lib.ts';

const root = fileURLToPath(new URL('..', import.meta.url));
const exportFile = `${root}../../design/tokens-export.json`;
const scopeFile = `${root}design/tokens-scope.json`;
const jsonFile = `${root}design/tokens.json`;
const cssFile = `${root}src/styles/tokens.css`;

const doc = JSON.parse(readFileSync(exportFile, 'utf8')) as FigmaExport;
const scope = JSON.parse(readFileSync(scopeFile, 'utf8')) as TokenScope;
const items = buildTokensJson(doc, scope);
const outputs: [string, string][] = [
  [jsonFile, tokensJsonText(items)],
  [cssFile, buildTokensCss(items)],
];

if (process.argv.includes('--check')) {
  const stale = outputs.filter(([file, text]) => readFileSync(file, 'utf8') !== text);
  for (const [file] of stale) console.error(`out of date (npm run gen:tokens): ${file}`);
  process.exitCode = stale.length > 0 ? 1 : 0;
} else {
  for (const [file, text] of outputs) writeFileSync(file, text);
  console.log(
    `tokens: ${String(items.length)} of the export's tokens (${String(scope.unused.length)} left out) → ${jsonFile} → ${cssFile}`,
  );
}
