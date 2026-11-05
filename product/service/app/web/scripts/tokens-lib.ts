// Pure token helpers shared by scripts/gen-tokens.ts and the unit tests.
// Pipeline (TASKS P1-12): the Figma export (product/service/design/tokens-export.json, three
// collections) + the phase-1 scope (design/tokens-scope.json) → design/tokens.json →
// src/styles/tokens.css. Both outputs are generated; edit the export or the scope instead.

export type TokenLayer = 'primitive' | 'semantic' | 'component';
export type TokenType = 'color' | 'number' | 'string';

export interface FontSource {
  license: string;
  url: string;
  installed: boolean;
  commercial_use: boolean;
}

/** Fields the Figma export does not carry, kept per token in the scope file. */
export interface TokenNotes {
  font_source?: FontSource;
  use?: string;
}

export interface TokenItem extends TokenNotes {
  name: string;
  layer: TokenLayer;
  type: TokenType;
  value?: string | number;
  alias?: string;
  status?: string;
}

export const LAYER_ORDER: readonly TokenLayer[] = ['primitive', 'semantic', 'component'];

// ── Figma export → tokens.json ─────────────────────────────────────────────

export interface FigmaColor {
  r: number;
  g: number;
  b: number;
  a: number;
}

export interface FigmaAlias {
  type: 'VARIABLE_ALIAS';
  ref: string;
}

export type FigmaValue = FigmaColor | FigmaAlias | number | string;

export interface FigmaVariable {
  type: 'COLOR' | 'FLOAT' | 'STRING';
  value: { mode: string; value: FigmaValue }[];
  scopes?: string[];
}

export interface FigmaExport {
  source?: string;
  collections: Record<TokenLayer, Record<string, FigmaVariable>>;
  textStyles?: unknown[];
}

/** design/tokens-scope.json: which export tokens phase 1 uses. */
export interface TokenScope {
  about?: string[];
  status: string;
  /** Figma font family → CSS family ('Pretendard Variable' → 'Pretendard'). */
  fontRename: Record<string, string>;
  /** Tokens in use, in tokens.json order (the layer comes from the export collection). */
  used: string[];
  /** Export tokens left out of phase 1 (listed so a new Figma token cannot slip in unseen). */
  unused: string[];
  notes: Record<string, TokenNotes>;
}

const TYPE_OF: Record<FigmaVariable['type'], TokenType> = {
  COLOR: 'color',
  FLOAT: 'number',
  STRING: 'string',
};

function isAlias(v: FigmaValue): v is FigmaAlias {
  // The export is read as JSON, so check the tag at run time too.
  return typeof v === 'object' && 'ref' in v && (v as { type?: unknown }).type === 'VARIABLE_ALIAS';
}

function isColor(v: FigmaValue): v is FigmaColor {
  return typeof v === 'object' && 'r' in v;
}

/** Figma rgba channels (0–1) → `#RRGGBB`, plus `AA` when not opaque. Upper case. */
export function figmaColorHex({ r, g, b, a }: FigmaColor): string {
  const hex = (c: number) =>
    Math.round(c * 255)
      .toString(16)
      .toUpperCase()
      .padStart(2, '0');
  return `#${hex(r)}${hex(g)}${hex(b)}${a === 1 ? '' : hex(a)}`;
}

/** `primitive/color/neutral/1` → `color/neutral/1` (the export prefixes the collection). */
export function figmaAliasTarget(ref: string): { layer: string; name: string } {
  const cut = ref.indexOf('/');
  if (cut <= 0) throw new Error(`Alias ref without a collection: ${ref}`);
  return { layer: ref.slice(0, cut), name: ref.slice(cut + 1) };
}

/** One export variable → one tokens.json item (value or alias, then status and notes). */
export function exportToken(
  name: string,
  layer: TokenLayer,
  variable: FigmaVariable,
  scope: Pick<TokenScope, 'status' | 'fontRename' | 'notes'>,
): TokenItem {
  if (variable.value.length !== 1) {
    throw new Error(`Token ${name} has ${String(variable.value.length)} modes; phase 1 has one`);
  }
  const raw = variable.value[0]?.value;
  if (raw === undefined) throw new Error(`Token ${name} has no value`);
  const type = TYPE_OF[variable.type];
  const item: TokenItem = { name, layer, type };
  if (isAlias(raw)) {
    item.alias = figmaAliasTarget(raw.ref).name;
  } else if (variable.type === 'COLOR' && isColor(raw)) {
    item.value = figmaColorHex(raw);
  } else if (variable.type === 'FLOAT' && typeof raw === 'number') {
    item.value = raw;
  } else if (variable.type === 'STRING' && typeof raw === 'string') {
    item.value = scope.fontRename[raw] ?? raw;
  } else {
    throw new Error(`Token ${name}: ${variable.type} value has the wrong shape`);
  }
  item.status = scope.status;
  return { ...item, ...scope.notes[name] };
}

/**
 * Build tokens.json from the export and the scope. Fails when an export token is in neither
 * (or both) of the scope lists, a scoped name is missing from the export, an alias
 * points outside the scope or at the wrong collection, or a note names an unscoped token.
 */
export function buildTokensJson(doc: FigmaExport, scope: TokenScope): TokenItem[] {
  const exported = new Map<string, { layer: TokenLayer; variable: FigmaVariable }>();
  for (const layer of LAYER_ORDER) {
    for (const [name, variable] of Object.entries(doc.collections[layer])) {
      if (exported.has(name)) throw new Error(`Export has ${name} in two collections`);
      exported.set(name, { layer, variable });
    }
  }
  const seen = new Set<string>();
  for (const name of [...scope.used, ...scope.unused]) {
    if (seen.has(name)) throw new Error(`Scope lists ${name} twice`);
    if (!exported.has(name)) throw new Error(`Scope lists ${name}, which the export does not have`);
    seen.add(name);
  }
  const unclassified = [...exported.keys()].filter((name) => !seen.has(name));
  if (unclassified.length > 0) {
    throw new Error(`Export tokens in neither scope list: ${unclassified.join(', ')}`);
  }
  const items = scope.used.map((name) => {
    const found = exported.get(name);
    if (found === undefined) throw new Error(`Export has no ${name}`);
    return exportToken(name, found.layer, found.variable, scope);
  });
  const usedNames = new Set(scope.used);
  for (const [name, notes] of Object.entries(scope.notes)) {
    if (!usedNames.has(name)) throw new Error(`Scope notes name ${name}, which is not used`);
    const extra = Object.keys(notes).filter((k) => k !== 'font_source' && k !== 'use');
    if (extra.length > 0) throw new Error(`Scope notes for ${name} carry ${extra.join(', ')}`);
  }
  for (const item of items) {
    const raw = exported.get(item.name)?.variable.value[0]?.value;
    if (raw === undefined || !isAlias(raw)) continue;
    const target = figmaAliasTarget(raw.ref);
    if (!usedNames.has(target.name)) {
      throw new Error(`${item.name} aliases ${target.name}, which is not in the phase-1 scope`);
    }
    if (exported.get(target.name)?.layer !== target.layer) {
      throw new Error(`${item.name} aliases ${raw.ref}, which is not in that collection`);
    }
  }
  return items;
}

/** tokens.json text: two-space JSON plus a final newline. */
export function tokensJsonText(items: readonly TokenItem[]): string {
  return `${JSON.stringify(items, null, 2)}\n`;
}

// ── tokens.json → tokens.css ───────────────────────────────────────────────

/** `bg/default` → `--bg-default` (Figma variable name with `/` replaced by `-`). */
export function cssVarName(name: string): string {
  return `--${name.replaceAll('/', '-')}`;
}

/** Font weights are unitless; every other number token is a pixel length. */
function isUnitless(name: string): boolean {
  return name.startsWith('font/weight/');
}

export function primitiveCssValue(item: TokenItem): string {
  if (item.value === undefined) {
    throw new Error(`Primitive token ${item.name} has no value`);
  }
  switch (item.type) {
    case 'color':
      return String(item.value);
    case 'number':
      return isUnitless(item.name) ? String(item.value) : `${String(item.value)}px`;
    case 'string':
      return JSON.stringify(String(item.value));
  }
}

export function indexTokens(items: readonly TokenItem[]): Map<string, TokenItem> {
  const map = new Map<string, TokenItem>();
  for (const item of items) {
    if (map.has(item.name)) throw new Error(`Duplicate token ${item.name}`);
    map.set(item.name, item);
  }
  return map;
}

/** Follow the alias chain to the primitive that carries the value. */
export function resolveToken(name: string, map: ReadonlyMap<string, TokenItem>): TokenItem {
  const seen: string[] = [];
  let current = map.get(name);
  while (current) {
    if (seen.includes(current.name)) {
      throw new Error(`Alias cycle: ${[...seen, current.name].join(' → ')}`);
    }
    seen.push(current.name);
    if (current.alias === undefined) {
      if (current.layer !== 'primitive' || current.value === undefined) {
        throw new Error(`Token ${current.name} has neither alias nor primitive value`);
      }
      return current;
    }
    current = map.get(current.alias);
  }
  throw new Error(`Unresolvable token chain: ${[...seen, '?'].join(' → ')} (from ${name})`);
}

export function cssDeclaration(item: TokenItem): string {
  const value =
    item.alias !== undefined ? `var(${cssVarName(item.alias)})` : primitiveCssValue(item);
  return `  ${cssVarName(item.name)}: ${value};`;
}

/** Build tokens.css: one :root block, layer by layer, aliases as var() chains. */
export function buildTokensCss(items: readonly TokenItem[]): string {
  const map = indexTokens(items);
  for (const item of items) resolveToken(item.name, map); // fail fast on broken chains
  const lines: string[] = [
    '/* Generated by scripts/gen-tokens.ts from design/tokens.json. Do not edit. */',
    ':root {',
  ];
  for (const layer of LAYER_ORDER) {
    const layerItems = items.filter((i) => i.layer === layer);
    lines.push(`  /* ${layer} (${String(layerItems.length)}) */`);
    for (const item of layerItems) lines.push(cssDeclaration(item));
  }
  lines.push('}', '');
  return lines.join('\n');
}
