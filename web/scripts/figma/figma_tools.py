#!/usr/bin/env python3
"""Figma reading and visual-check helpers for web/ (figma-bridge plugin path only).

  dump    <ids,comma> <out.json> [--descend] [--paths]   geometry + token bindings via plugin exec
  show    <dump.json> <id|name> [--depth N]              one line per node, bound values as tokens
  export  <kit.json> <outDir> [--scale 2]                export the Figma nodes listed in a kit run
  compare <kitDir> <figDir> [--sheet out.png id ...]     size deltas + mean abs diff, or a side-by-side sheet

The file must be open in Figma desktop with the bridge plugin connected
(python3 ~/tools/figma-bridge/figma.py setup). Never writes to Figma.
Kit screenshots come from scripts/figma/shoot-kit.mjs (dev server on /_kit?only=<id>).
"""
import json
import os
import re
import subprocess
import sys

FILE_URL = 'https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev'
BRIDGE = os.path.expanduser('~/tools/figma-bridge/figma.py')
HERE = os.path.dirname(os.path.abspath(__file__))


def bridge(*args):
    return subprocess.run(['python3', BRIDGE, *args], capture_output=True, text=True)


def cmd_dump(ids, out, descend=False, paths=False):
    src = open(os.path.join(HERE, 'dump.js')).read()
    job = (src.replace('__ROOTS__', json.dumps(ids.split(',')))
              .replace('__DESCEND__', 'true' if descend else 'false')
              .replace('__PATHS__', 'true' if paths else 'false'))
    tmp = out + '.job.js'
    open(tmp, 'w').write(job)
    r = bridge('exec', FILE_URL, '--file', tmp, '--save', out)
    os.remove(tmp)
    if r.returncode != 0:
        sys.exit(r.stderr[-500:])
    print(out, os.path.getsize(out), 'bytes')


def fmt_paint(ps):
    return ','.join(p.get('v') or p.get('c') or p.get('t', '') for p in ps)


def tok(bv, key, val):
    if bv and key in bv:
        v = bv[key]
        return v[0] if isinstance(v, list) else v
    return val


def line(n):
    bv = dict(n.get('bv') or {})
    parts = [f"{n['ty'][:4]} '{n['nm']}'"]
    if n.get('hidden'):
        parts.append('HIDDEN')
    if 'w' in n:
        parts.append(f"{tok(bv, 'width', n['w'])}x{tok(bv, 'height', n['h'])}")
    if 'x' in n:
        parts.append(f"@{n['x']},{n['y']}")
    if n.get('lay'):
        t, r, b, l = n['pad']
        pad = [tok(bv, 'paddingTop', t), tok(bv, 'paddingRight', r), tok(bv, 'paddingBottom', b), tok(bv, 'paddingLeft', l)]
        parts.append(f"{n['lay'][:1]} pad{pad} gap:{tok(bv, 'itemSpacing', n['gap'])} al:{n['al']} sz:{n['sz']}")
    if 'rad' in n:
        parts.append(f"rad:{bv.get('topLeftRadius', n['rad'])}")
    if n.get('fill'):
        parts.append('fill=' + fmt_paint(n['fill']))
    if n.get('stroke'):
        parts.append('stroke=' + fmt_paint(n['stroke']) + f" w{n.get('sw')} {n.get('sa', '')}" + (f" dash{n['dash']}" if n.get('dash') else ''))
    if 'op' in n:
        parts.append(f"op{n['op']}")
    if n.get('arc'):
        parts.append(f"arc{n['arc']}")
    if n['ty'] == 'TEXT':
        parts.append(f"\"{n['txt']}\" style={n.get('tstyle')} [{n['font']} {n['fs']}/{n['lh']}]")
    if n['ty'] == 'INSTANCE':
        parts.append(f"<{n.get('main')}>")
    if n.get('path'):
        parts.append(f"PATH[{n['path'][:200]}]")
    return ' '.join(str(p) for p in parts)


def cmd_show(path, key, depth=99):
    data = json.load(open(path))['value']

    def find(n, acc):
        if n.get('id') == key or key in n.get('nm', ''):
            acc.append(n)
        for c in n.get('ch', []):
            find(c, acc)

    def walk(n, d):
        print('  ' * d + line(n))
        if d < depth:
            for c in n.get('ch', []):
                walk(c, d + 1)

    hits = []
    for root in data.values():
        find(root, hits)
    if not hits:
        sys.exit('not found')
    walk(hits[0], 0)


def cmd_export(kit_json, out_dir, scale='2'):
    os.makedirs(out_dir, exist_ok=True)
    ids = [i for i in json.load(open(kit_json))['sizes'] if re.fullmatch(r'\d+:\d+', i)]
    for i in ids:
        target = os.path.join(out_dir, i.replace(':', '-') + '.png')
        if os.path.exists(target):
            continue
        r = bridge('export', FILE_URL, '--node', i, '--scale', scale, '--out', out_dir)
        m = re.search(r'"saved":\s*"([^"]+)"', r.stdout)
        if m and os.path.exists(m.group(1)) and m.group(1) != target:
            os.rename(m.group(1), target)
    print(len(ids), 'nodes exported to', out_dir)


def cmd_compare(kit_dir, fig_dir, sheet=None, sheet_ids=()):
    from PIL import Image, ImageChops, ImageDraw, ImageStat

    def load(p):
        im = Image.open(p).convert('RGBA')
        bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        return bg.convert('RGB')

    if sheet:
        pairs = [(i, load(f"{fig_dir}/{i.replace(':', '-')}.png"), load(f"{kit_dir}/{i.replace(':', '-')}.png")) for i in sheet_ids]
        width = max(a.width + b.width for _, a, b in pairs) + 48
        height = sum(max(a.height, b.height) + 28 for _, a, b in pairs) + 16
        out = Image.new('RGB', (width, height), (235, 235, 235))
        draw = ImageDraw.Draw(out)
        y = 16
        for i, a, b in pairs:
            draw.text((16, y), f'{i}  figma | kit', fill=(80, 80, 80))
            y += 14
            out.paste(a, (16, y))
            out.paste(b, (32 + a.width, y))
            y += max(a.height, b.height) + 14
        out.save(sheet)
        print('sheet', sheet, out.size)
        return
    for name in sorted(os.listdir(kit_dir)):
        f = os.path.join(fig_dir, name)
        if not name.endswith('.png') or not os.path.exists(f):
            continue
        a, b = load(f), load(os.path.join(kit_dir, name))
        w, h = min(a.width, b.width), min(a.height, b.height)
        mad = sum(ImageStat.Stat(ImageChops.difference(a.crop((0, 0, w, h)), b.crop((0, 0, w, h)))).mean) / 3
        dw, dh = (b.width - a.width) / 2, (b.height - a.height) / 2
        flag = '' if abs(dw) < 0.6 and abs(dh) < 0.6 else '  <-- size'
        print(f"{name[:-4]:>12}  figma {a.width / 2:7.1f}x{a.height / 2:<6.1f} dW {dw:+5.1f} dH {dh:+5.1f}  mad {mad:5.1f}{flag}")


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    cmd, args = argv[1], argv[2:]
    flags = {a for a in args if a.startswith('--')}
    if cmd == 'dump':
        cmd_dump(args[0], args[1], '--descend' in flags, '--paths' in flags)
    elif cmd == 'show':
        depth = int(args[args.index('--depth') + 1]) if '--depth' in args else 99
        cmd_show(args[0], args[1], depth)
    elif cmd == 'export':
        scale = args[args.index('--scale') + 1] if '--scale' in args else '2'
        cmd_export(args[0], args[1], scale)
    elif cmd == 'compare':
        if '--sheet' in args:
            i = args.index('--sheet')
            cmd_compare(args[0], args[1], args[i + 1], args[i + 2:])
        else:
            cmd_compare(args[0], args[1])
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv)
