// ops notes: screens use semantic/component tokens only — zero color, spacing or
// font-size literals. This scans every stylesheet and component source.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

const srcDir = join(process.cwd(), 'src');

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

const files = walk(srcDir);
const cssFiles = files.filter((f) => f.endsWith('.css') && !f.endsWith('tokens.css'));
const tsxFiles = files.filter((f) => /\.tsx?$/.test(f));
const tokensCss = readFileSync(join(srcDir, 'styles/tokens.css'), 'utf8');
const tokenVars = new Set([...tokensCss.matchAll(/(--[\w-]+):/g)].map((m) => m[1]));

/** `prop: value;` pairs outside of comments. */
function declarations(css: string): { prop: string; value: string }[] {
  const clean = css
    .replace(/\/\*[\s\S]*?\*\//g, '')
    // @font-face holds descriptors (font-weight: 45 920), not properties.
    .replace(/@font-face\s*\{[^}]*\}/g, '');
  return [...clean.matchAll(/([\w-]+)\s*:\s*([^;{}]+);/g)].map((m) => ({
    prop: (m[1] ?? '').trim(),
    value: (m[2] ?? '').trim(),
  }));
}

const COLOR_LITERAL =
  /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\b(white|black|red|blue|green|gray|grey|purple|orange|yellow)\b/;
const SPACING_PROPS = /^(padding|margin|gap|row-gap|column-gap|inset|scroll-padding)(-[\w-]+)?$/;
const FONT_PROPS = /^(font-size|line-height|font-weight)$/;
const LENGTH_LITERAL = /(^|[\s(,+*-])\d*\.?\d+(px|rem|em)\b/;

describe('stylesheets', () => {
  it('found the stylesheets to check', () => {
    expect(cssFiles.length).toBeGreaterThan(10);
  });

  for (const file of cssFiles) {
    const name = relative(srcDir, file);
    const css = readFileSync(file, 'utf8');
    const decls = declarations(css);

    it(`${name}: no color literals`, () => {
      const bad = decls.filter((d) => !d.prop.startsWith('--') && COLOR_LITERAL.test(d.value));
      expect(bad).toEqual([]);
    });

    it(`${name}: no font-size / line-height / font-weight literals`, () => {
      const bad = decls.filter((d) => FONT_PROPS.test(d.prop) && !d.value.startsWith('var('));
      expect(bad).toEqual([]);
    });

    it(`${name}: no spacing literals (padding, margin, gap, inset)`, () => {
      // Lengths may appear only through var(); a bare 0 is fine.
      const bad = decls.filter((d) => {
        if (!SPACING_PROPS.test(d.prop)) return false;
        const stripped = d.value.replace(/var\([^)]*\)/g, 'V').replace(/env\([^)]*\)/g, 'E');
        return LENGTH_LITERAL.test(stripped);
      });
      expect(bad).toEqual([]);
    });

    it(`${name}: every var() is a token or a custom property set in this file`, () => {
      const local = new Set([...css.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]));
      const unknown = [...css.matchAll(/var\((--[\w-]+)/g)]
        .map((m) => m[1])
        .filter((v) => !tokenVars.has(v) && !local.has(v));
      expect(unknown).toEqual([]);
    });
  }
});

describe('components', () => {
  it('have no hex colors in TSX/TS sources', () => {
    const bad = tsxFiles.filter((f) => /['"`]#[0-9a-fA-F]{3,8}['"`]/.test(readFileSync(f, 'utf8')));
    expect(bad.map((f) => relative(srcDir, f))).toEqual([]);
  });

  it('keep user-visible Korean copy in copy.ts (screens and components)', () => {
    // Korean string literals are allowed only in copy.ts (and per-screen copy/*.ts), fixtures
    // and lib/labels.
    const allowed = /(^copy\.ts$|^copy\/|^fixtures\/|^kit\/)/;
    const hangulLiteral = /(['"`])[^'"`\n]*[가-힣][^'"`\n]*\1/;
    const bad = tsxFiles
      .map((f) => relative(srcDir, f))
      .filter((rel) => !allowed.test(rel))
      .filter((rel) => {
        const code = readFileSync(join(srcDir, rel), 'utf8')
          .replace(/\/\*[\s\S]*?\*\//g, '')
          .replace(/\/\/.*$/gm, '');
        return hangulLiteral.test(code);
      });
    expect(bad).toEqual([]);
  });
});
