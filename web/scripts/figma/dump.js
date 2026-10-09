// Figma plugin job (read-only): dumps geometry and token bindings of the given nodes.
// Run through scripts/figma/figma_tools.py dump — it fills __ROOTS__, __DESCEND__, __PATHS__.
// Variables from the confirmed collections (원시 · 의미 · 컴포넌트) print by name;
// any other collection prints as name@collection so stray bindings stand out.
const ROOTS = __ROOTS__;
const DESCEND_INST = __DESCEND__;
const varCache = {};
const colCache = {};
async function varName(id) {
  if (!id) return null;
  if (varCache[id] !== undefined) return varCache[id];
  const v = await figma.variables.getVariableByIdAsync(id);
  if (!v) { varCache[id] = '?' + id; return varCache[id]; }
  let col = colCache[v.variableCollectionId];
  if (col === undefined) {
    const c = await figma.variables.getVariableCollectionByIdAsync(v.variableCollectionId);
    col = c ? c.name : '?';
    colCache[v.variableCollectionId] = col;
  }
  varCache[id] = col === '원시' || col === '의미' || col === '컴포넌트' ? v.name : `${v.name}@${col}`;
  return varCache[id];
}
const r2 = (x) => (typeof x === 'number' ? Math.round(x * 100) / 100 : x);
function hex(c, a) {
  const h = (v) => Math.round(v * 255).toString(16).padStart(2, '0');
  let s = '#' + h(c.r) + h(c.g) + h(c.b);
  if (a !== undefined && a < 1) s += h(a);
  return s.toUpperCase();
}
async function paints(arr) {
  if (!arr || arr === figma.mixed) return arr === figma.mixed ? 'mixed' : undefined;
  const out = [];
  for (const p of arr) {
    if (p.visible === false) continue;
    const o = { t: p.type };
    if (p.type === 'SOLID') o.c = hex(p.color, p.opacity);
    if (p.boundVariables && p.boundVariables.color) o.v = await varName(p.boundVariables.color.id);
    if (p.type === 'IMAGE') o.img = true;
    if (p.type.startsWith('GRADIENT')) o.stops = p.gradientStops.map((s) => hex(s.color, s.color.a));
    if (p.opacity !== undefined && p.opacity < 1 && p.type !== 'SOLID') o.o = r2(p.opacity);
    out.push(o);
  }
  return out.length ? out : undefined;
}
async function bound(n) {
  const bv = n.boundVariables;
  if (!bv) return undefined;
  const o = {};
  for (const k of Object.keys(bv)) {
    if (k === 'fills' || k === 'strokes') continue;
    const val = bv[k];
    if (Array.isArray(val)) {
      const names = [];
      for (const x of val) names.push(await varName(x.id));
      o[k] = names;
    } else if (val && val.id) {
      o[k] = await varName(val.id);
    }
  }
  return Object.keys(o).length ? o : undefined;
}
async function walk(n, depth) {
  const o = { id: n.id, ty: n.type, nm: n.name };
  if (n.visible === false) o.hidden = true;
  if ('width' in n) { o.w = r2(n.width); o.h = r2(n.height); }
  if (depth > 0 && 'x' in n) { o.x = r2(n.x); o.y = r2(n.y); }
  if ('opacity' in n && n.opacity < 1) o.op = r2(n.opacity);
  if ('layoutMode' in n && n.layoutMode !== 'NONE') {
    o.lay = n.layoutMode;
    o.pad = [n.paddingTop, n.paddingRight, n.paddingBottom, n.paddingLeft].map(r2);
    o.gap = r2(n.itemSpacing);
    o.al = [n.primaryAxisAlignItems, n.counterAxisAlignItems].join('/');
    o.sz = [n.primaryAxisSizingMode, n.counterAxisSizingMode].join('/');
    if (n.layoutWrap === 'WRAP') { o.wrap = true; o.cgap = n.counterAxisSpacing; }
  }
  if ('layoutSizingHorizontal' in n && depth > 0) o.lsz = n.layoutSizingHorizontal + '/' + n.layoutSizingVertical;
  if ('layoutPositioning' in n && n.layoutPositioning === 'ABSOLUTE') o.abs = true;
  if ('strokesIncludedInLayout' in n && n.strokesIncludedInLayout) o.sil = true;
  if ('layoutGrow' in n && n.layoutGrow) o.grow = n.layoutGrow;
  if ('textTruncation' in n && n.textTruncation === 'ENDING') o.trunc = n.maxLines || true;
  if ('constraints' in n && depth > 0 && n.parent && n.parent.layoutMode === 'NONE') o.cons = n.constraints.horizontal + '/' + n.constraints.vertical;
  if ('minWidth' in n && n.minWidth) o.minW = n.minWidth;
  if ('maxWidth' in n && n.maxWidth) o.maxW = n.maxWidth;
  if ('cornerRadius' in n) {
    if (n.cornerRadius === figma.mixed) o.rad = [n.topLeftRadius, n.topRightRadius, n.bottomRightRadius, n.bottomLeftRadius];
    else if (n.cornerRadius) o.rad = r2(n.cornerRadius);
  }
  if ('fills' in n) { const f = await paints(n.fills); if (f) o.fill = f; }
  if ('strokes' in n) {
    const s = await paints(n.strokes);
    if (s) {
      o.stroke = s;
      o.sw = n.strokeWeight === figma.mixed ? [n.strokeTopWeight, n.strokeRightWeight, n.strokeBottomWeight, n.strokeLeftWeight] : r2(n.strokeWeight);
      o.sa = n.strokeAlign;
      if (n.dashPattern && n.dashPattern.length) o.dash = n.dashPattern;
      if (n.strokeCap && n.strokeCap !== 'NONE' && n.strokeCap !== figma.mixed) o.cap = n.strokeCap;
    }
  }
  if ('effects' in n && n.effects.length) o.fx = n.effects.filter((e) => e.visible !== false).map((e) => ({ t: e.type, r: e.radius, off: e.offset, c: e.color ? hex(e.color, e.color.a) : undefined, sp: e.spread }));
  if ('clipsContent' in n && n.clipsContent && n.type !== 'COMPONENT') o.clip = true;
  if ('rotation' in n && n.rotation) o.rot = r2(n.rotation);
  const b = await bound(n);
  if (b) o.bv = b;
  if (n.type === 'ELLIPSE' && n.arcData && (n.arcData.endingAngle - n.arcData.startingAngle < 6.28 || n.arcData.innerRadius > 0)) o.arc = {s: r2(n.arcData.startingAngle), e: r2(n.arcData.endingAngle), ir: r2(n.arcData.innerRadius)};
  if ((n.type === 'VECTOR' || n.type === 'LINE') && __PATHS__) { try { o.path = n.vectorPaths.map(p => p.data).join(' | ').slice(0, 4000); } catch (e) {} }
  if (n.type === 'TEXT') {
    o.txt = n.characters;
    const fn = n.fontName;
    o.font = fn === figma.mixed ? 'mixed' : fn.family + ' ' + fn.style;
    o.fs = n.fontSize === figma.mixed ? 'mixed' : n.fontSize;
    const lh = n.lineHeight;
    o.lh = lh === figma.mixed ? 'mixed' : lh.unit === 'AUTO' ? 'auto' : lh.unit === 'PIXELS' ? lh.value : lh.value + '%';
    const ls = n.letterSpacing;
    if (ls !== figma.mixed && ls.value) o.ls = ls.unit === 'PIXELS' ? ls.value : ls.value + '%';
    o.ta = n.textAlignHorizontal;
    if (n.textAutoResize !== 'WIDTH_AND_HEIGHT') o.tar = n.textAutoResize;
    if (n.textDecoration && n.textDecoration !== 'NONE' && n.textDecoration !== figma.mixed) o.deco = n.textDecoration;
    if (n.textStyleId && n.textStyleId !== figma.mixed) {
      const st = await figma.getStyleByIdAsync(n.textStyleId);
      if (st) o.tstyle = st.name;
    }
    if (n.fontName === figma.mixed || n.fontSize === figma.mixed) {
      o.segs = n.getStyledTextSegments(['fontName', 'fontSize', 'fills']).map((s) => ({ t: s.characters, f: s.fontName.style, s: s.fontSize, c: s.fills[0] && s.fills[0].color ? hex(s.fills[0].color) : undefined }));
    }
  }
  if (n.type === 'INSTANCE') {
    const mc = await n.getMainComponentAsync();
    if (mc) {
      o.main = mc.parent && mc.parent.type === 'COMPONENT_SET' ? mc.parent.name + '/' + mc.name : mc.name;
      o.mainId = mc.id;
    }
    const cp = n.componentProperties;
    if (cp && Object.keys(cp).length) {
      o.props = {};
      for (const k of Object.keys(cp)) o.props[k] = cp[k].value;
    }
    // Do not descend into nested instance internals beyond a light summary for icon-like instances.
  }
  if ('children' in n && n.children.length && (n.type !== 'INSTANCE' || DESCEND_INST)) {
    o.ch = [];
    for (const c of n.children) o.ch.push(await walk(c, depth + 1));
  }
  return o;
}

const out = {};
for (const rid of ROOTS) {
  const n = await figma.getNodeByIdAsync(rid);
  out[rid] = n ? await walk(n, 0) : { missing: true };
}
return out;
