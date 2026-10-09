// Generates src/styles/tokens.css from design/tokens.json.
// Runs on Node's built-in type stripping: `node scripts/gen-tokens.ts`.
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { buildTokensCss, type TokenItem } from './tokens-lib.ts';

const root = fileURLToPath(new URL('..', import.meta.url));
const source = `${root}design/tokens.json`;
const target = `${root}src/styles/tokens.css`;

const items = JSON.parse(readFileSync(source, 'utf8')) as TokenItem[];
const css = buildTokensCss(items);
writeFileSync(target, css);
console.log(`tokens.css: ${String(items.length)} tokens → ${target}`);
