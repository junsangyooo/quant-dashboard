// Token pipeline (TASKS P1-12): Figma export + design/tokens-scope.json → design/tokens.json →
// src/styles/tokens.css. The committed outputs must be exactly what scripts/gen-tokens.ts writes.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  buildTokensCss,
  buildTokensJson,
  exportToken,
  figmaAliasTarget,
  figmaColorHex,
  tokensJsonText,
  type FigmaExport,
  type FigmaVariable,
  type TokenScope,
} from '../scripts/tokens-lib.ts';

const root = process.cwd();
const read = (p: string) => readFileSync(join(root, p), 'utf8');
const doc = JSON.parse(read('../../design/tokens-export.json')) as FigmaExport;
const scope = JSON.parse(read('design/tokens-scope.json')) as TokenScope;
const jsonText = read('design/tokens.json');
const css = read('src/styles/tokens.css');
const items = buildTokensJson(doc, scope);

const exportNames = Object.values(doc.collections).flatMap((c) => Object.keys(c));

function variable(type: FigmaVariable['type'], value: FigmaVariable['value'][0]['value']) {
  return { type, value: [{ mode: 'Mode 1', value }] } satisfies FigmaVariable;
}

describe('export → tokens.json → tokens.css', () => {
  it('committed design/tokens.json is what the export and the scope give (npm run gen:tokens)', () => {
    expect(jsonText).toBe(tokensJsonText(items));
  });

  it('committed src/styles/tokens.css is what the generated tokens.json gives', () => {
    expect(css).toBe(buildTokensCss(items));
  });

  it('the export has 223 tokens in three collections', () => {
    expect(Object.keys(doc.collections)).toEqual(['primitive', 'semantic', 'component']);
    expect(exportNames).toHaveLength(223);
    expect(new Set(exportNames).size).toBe(223);
  });

  it('phase 1 uses 180 of them (66 · 78 · 36) and lists the other 43', () => {
    expect(items).toHaveLength(180);
    expect(items.filter((i) => i.layer === 'primitive')).toHaveLength(66);
    expect(items.filter((i) => i.layer === 'semantic')).toHaveLength(78);
    expect(items.filter((i) => i.layer === 'component')).toHaveLength(36);
    expect(scope.unused).toHaveLength(43);
    expect([...scope.used, ...scope.unused].sort()).toEqual([...exportNames].sort());
  });

  it('every generated token keeps its export collection as its layer', () => {
    for (const item of items) {
      const layer = Object.entries(doc.collections).find(([, c]) => item.name in c)?.[0];
      expect(layer, item.name).toBe(item.layer);
    }
  });

  it('renames the Figma font family so tokens.css stays as it is', () => {
    expect(doc.collections.primitive['font/family/sans']?.value[0]?.value).toBe(
      'Pretendard Variable',
    );
    expect(items.find((i) => i.name === 'font/family/sans')?.value).toBe('Pretendard');
    expect(css).toContain('--font-family-sans: "Pretendard";');
    expect(css).not.toContain('Pretendard Variable');
  });
});

describe('export conversion', () => {
  const s = { status: 'confirmed', fontRename: { 'Pretendard Variable': 'Pretendard' }, notes: {} };

  it('turns Figma colors into upper-case hex, with alpha only when not opaque', () => {
    expect(figmaColorHex({ r: 1, g: 1, b: 1, a: 1 })).toBe('#FFFFFF');
    expect(
      figmaColorHex({
        r: 0.09803921729326248,
        g: 0.12156862765550613,
        b: 0.1568627506494522,
        a: 0.501960813999176,
      }),
    ).toBe('#191F2880');
  });

  it('drops the collection from alias refs', () => {
    expect(figmaAliasTarget('primitive/color/neutral/1')).toEqual({
      layer: 'primitive',
      name: 'color/neutral/1',
    });
    expect(() => figmaAliasTarget('color')).toThrow(/collection/);
  });

  it('maps types and values, then adds status and notes', () => {
    expect(exportToken('space/4', 'primitive', variable('FLOAT', 4), s)).toEqual({
      name: 'space/4',
      layer: 'primitive',
      type: 'number',
      value: 4,
      status: 'confirmed',
    });
    const alias = variable('COLOR', { type: 'VARIABLE_ALIAS', ref: 'primitive/color/neutral/1' });
    expect(
      exportToken('bg/default', 'semantic', alias, { ...s, notes: { 'bg/default': { use: 'x' } } }),
    ).toEqual({
      name: 'bg/default',
      layer: 'semantic',
      type: 'color',
      alias: 'color/neutral/1',
      status: 'confirmed',
      use: 'x',
    });
    expect(exportToken('f', 'primitive', variable('STRING', 'Pretendard Variable'), s).value).toBe(
      'Pretendard',
    );
  });

  it('refuses more than one mode and values of the wrong shape', () => {
    const twoModes: FigmaVariable = {
      type: 'FLOAT',
      value: [
        { mode: 'Light', value: 1 },
        { mode: 'Dark', value: 2 },
      ],
    };
    expect(() => exportToken('x', 'primitive', twoModes, s)).toThrow(/modes/);
    expect(() => exportToken('x', 'primitive', variable('FLOAT', 'a'), s)).toThrow(/shape/);
  });
});

describe('scope checks', () => {
  const tiny: FigmaExport = {
    collections: {
      primitive: { 'space/4': variable('FLOAT', 4), 'space/8': variable('FLOAT', 8) },
      semantic: {
        'space/tight': variable('FLOAT', { type: 'VARIABLE_ALIAS', ref: 'primitive/space/4' }),
      },
      component: {},
    },
  };
  const base: TokenScope = {
    status: 'confirmed',
    fontRename: {},
    used: ['space/4', 'space/tight'],
    unused: ['space/8'],
    notes: {},
  };

  it('builds the scoped tokens in scope order', () => {
    expect(buildTokensJson(tiny, base).map((i) => i.name)).toEqual(['space/4', 'space/tight']);
  });

  it('fails on an export token in neither list (a new Figma token)', () => {
    expect(() => buildTokensJson(tiny, { ...base, unused: [] })).toThrow(/neither/);
  });

  it('fails on a token listed twice or not in the export', () => {
    expect(() => buildTokensJson(tiny, { ...base, unused: ['space/8', 'space/4'] })).toThrow(
      /twice/,
    );
    expect(() => buildTokensJson(tiny, { ...base, used: [...base.used, 'space/99'] })).toThrow(
      /does not have/,
    );
  });

  it('fails when a used token aliases a token outside the scope', () => {
    expect(() =>
      buildTokensJson(tiny, { ...base, used: ['space/8', 'space/tight'], unused: ['space/4'] }),
    ).toThrow(/not in the phase-1 scope/);
  });

  it('fails on notes for an unused token or with unknown fields', () => {
    expect(() => buildTokensJson(tiny, { ...base, notes: { 'space/8': { use: 'x' } } })).toThrow(
      /not used/,
    );
    const odd = { 'space/4': { use: 'x', value: 5 } } as unknown as TokenScope['notes'];
    expect(() => buildTokensJson(tiny, { ...base, notes: odd })).toThrow(/carry value/);
  });
});
