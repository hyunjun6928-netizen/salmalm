#!/usr/bin/env python3
"""Bundle JS modules from static/js/ into static/app.js.

Usage:
  python scripts/bundle_js.py          # One-shot bundle
  python scripts/bundle_js.py --watch  # Watch mode (dev)
"""
import os, sys, glob

def bundle(src_dir, out_file):
    modules = sorted(glob.glob(os.path.join(src_dir, '*.js')))
    if not modules:
        print(f"No JS files in {src_dir}")
        return False

    parts = ['(function(){\n']
    for mod in modules:
        name = os.path.basename(mod)
        with open(mod, 'r') as f:
            content = f.read()
        parts.append(f'\n  /* ═══ {name} ═══ */\n')
        parts.append(content)
        parts.append('\n')
    parts.append('})();\n')

    result = ''.join(parts)

    if os.path.exists(out_file):
        with open(out_file, 'r') as f:
            if f.read() == result:
                return False

    with open(out_file, 'w') as f:
        f.write(result)

    n_lines = result.count('\n')
    print(f"✅ Bundled {len(modules)} modules → {out_file} ({n_lines} lines)")
    return True

if __name__ == '__main__':
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(base, 'salmalm', 'static', 'js')
    out = os.path.join(base, 'salmalm', 'static', 'app.js')

    if '--watch' in sys.argv:
        import time
        print(f"👀 Watching {src}...")
        while True:
            bundle(src, out)
            time.sleep(1)
    else:
        bundle(src, out)
