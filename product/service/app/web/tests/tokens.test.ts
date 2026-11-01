import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  buildTokensCss,
  cssVarName,
  indexTokens,
  resolveToken,
  type TokenItem,
} from '../scripts/tokens-lib.ts';

const root = process.cwd();
const items = JSON.parse(readFileSync(join(root, 'design/tokens.json'), 'utf8')) as TokenItem[];
const css = readFileSync(join(root, 'src/styles/tokens.css'), 'utf8');
const map = indexTokens(items);

describe('design/tokens.json (copy of project.json tokens.items)', () => {
  it('has 180 tokens: 66 primitive, 78 semantic, 36 component', () => {
    expect(items).toHaveLength(180);
    expect(items.filter((i) => i.layer === 'primitive')).toHaveLength(66);
    expect(items.filter((i) => i.layer === 'semantic')).toHaveLength(78);
    expect(items.filter((i) => i.layer === 'component')).toHaveLength(36);
  });

  it('primitives carry values and never alias', () => {
    for (const p of items.filter((i) => i.layer === 'primitive')) {
      expect(p.alias, p.name).toBeUndefined();
      expect(p.value, p.name).toBeDefined();
    }
  });

  it('every semantic and component token resolves to a primitive value', () => {
    for (const t of items.filter((i) => i.layer !== 'primitive')) {
      const resolved = resolveToken(t.name, map);
      expect(resolved.layer, t.name).toBe('primitive');
      expect(resolved.value, t.name).toBeDefined();
      expect(resolved.type, t.name).toBe(t.type);
    }
  });

  it('aliases only point down the layers (semantic → primitive, component → semantic|primitive)', () => {
    for (const t of items) {
      if (t.alias === undefined) continue;
      const target = map.get(t.alias);
      expect(target, `${t.name} → ${t.alias}`).toBeDefined();
      if (t.layer === 'semantic') expect(target?.layer).not.toBe('component');
    }
  });

  it('resolves known chains to their Figma values', () => {
    expect(resolveToken('bg/default', map).value).toBe('#FFFFFF');
    expect(resolveToken('calendar/ok', map).value).toBe('#E2DBFF'); // → chart/band → color/accent/0
    expect(resolveToken('toggle/radius', map).value).toBe(28);
    expect(resolveToken('type/body/size', map).value).toBe(15);
    expect(resolveToken('bg/scrim', map).value).toBe('#191F2880');
  });
});

describe('src/styles/tokens.css', () => {
  it('maps names by replacing / with -', () => {
    expect(cssVarName('bg/default')).toBe('--bg-default');
    expect(cssVarName('type/heading-1/line-height')).toBe('--type-heading-1-line-height');
  });

  it('is in sync with design/tokens.json (npm run gen:tokens)', () => {
    expect(css).toBe(buildTokensCss(items));
  });

  it('declares every token once, layer by layer, with var() chains for aliases', () => {
    for (const t of items) {
      const decl = new RegExp(`^  ${cssVarName(t.name)}: (.+);$`, 'm').exec(css);
      expect(decl, t.name).not.toBeNull();
      if (t.alias !== undefined) expect(decl?.[1]).toBe(`var(${cssVarName(t.alias)})`);
    }
    const order = ['/* primitive', '/* semantic', '/* component'].map((h) => css.indexOf(h));
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });

  it('only references variables it defines', () => {
    const defined = new Set([...css.matchAll(/^\s*(--[\w-]+):/gm)].map((m) => m[1]));
    for (const m of css.matchAll(/var\((--[\w-]+)\)/g)) expect(defined.has(m[1])).toBe(true);
  });

  it('gives font weights no unit and lengths px', () => {
    expect(css).toContain('--font-weight-semibold: 600;');
    expect(css).toContain('--space-16: 16px;');
    expect(css).toContain('--font-family-sans: "Pretendard";');
  });
});
